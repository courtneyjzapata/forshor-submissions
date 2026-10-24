"""Recoverable publication of the accepted catalog; never runs submitted Lean."""
from __future__ import annotations

import base64
import argparse
import copy
import datetime as dt
import json
import os
from pathlib import Path
import subprocess
import time
import urllib.error
import urllib.request


class RetryPublication(Exception):
    """A transient error or a competing snapshot requires a fresh state read."""


def publish_with_recovery(metadata, fetch_state, refresh_archive, estimate, send,
                          sleep=time.sleep, now=lambda: dt.datetime.now(dt.timezone.utc), attempts=4):
    key = metadata['evaluationKey']
    for attempt in range(attempts):
        try:
            state = fetch_state()
            completed = state.get('completedEvaluations', {}).get(key)
            if completed:
                if completed['headSha'] != metadata['headSha'] or completed['runId'] != metadata['runId']:
                    raise ValueError('Evaluation identity collision')
                return {'alreadyPublished': True, 'evaluationKey': key}
            archive, revision = refresh_archive()
            evaluation = {k: v for k, v in metadata.items() if k != 'evaluationKey'}
            previous = dt.datetime.fromisoformat(state['legacy']['lastUpdated'].replace('Z', '+00:00'))
            timestamp = max(now(), previous + dt.timedelta(milliseconds=1))
            evaluation.update(archiveCommit=revision, evaluatedAt=timestamp.isoformat(timespec='milliseconds').replace('+00:00', 'Z'))
            payload = estimate(archive, state, evaluation)
            payload['evaluationKey'] = key
            return send(payload)
        except RetryPublication:
            if attempt == attempts - 1:
                raise
            sleep(2 ** attempt)
    raise AssertionError('Unreachable')


def request_json(url, token, payload=None):
    request = urllib.request.Request(url, headers={'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'},
                                     data=json.dumps(payload).encode() if payload is not None else None)
    try:
        with urllib.request.urlopen(request, timeout=240) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        if error.code in (409, 408, 429) or error.code >= 500:
            raise RetryPublication(f'Publisher HTTP {error.code}; rereading current state') from None
        raise RuntimeError(f'Publisher rejected the request: HTTP {error.code}; inspect the publisher logs') from None
    except (urllib.error.URLError, TimeoutError) as error:
        raise RetryPublication('Publisher connection interrupted; checking whether publication succeeded') from error


def refresh_archive(path: Path):
    # checkout deliberately does not persist credentials. Supply a short-lived
    # GitHub token only in the child environment, never in argv or a remote URL.
    env = {**os.environ, 'GIT_CONFIG_COUNT': '1', 'GIT_CONFIG_KEY_0': 'http.https://github.com/.extraheader',
           'GIT_CONFIG_VALUE_0': 'AUTHORIZATION: basic ' + base64.b64encode(f"x-access-token:{os.environ['GH_TOKEN']}".encode()).decode()}
    subprocess.run(['git', '-C', str(path), 'fetch', '--depth=1', 'origin', 'submission-results'], env=env, check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run(['git', '-C', str(path), 'checkout', '--detach', 'FETCH_HEAD'], check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return path, subprocess.check_output(['git', '-C', str(path), 'rev-parse', 'HEAD'], text=True).strip()


def add_missing_attribution(archive, state):
    state = copy.deepcopy(state)
    attribution = state['provenance'].setdefault('attribution', [])
    known = {a['submissionId'] for a in attribution}
    index = json.loads((archive / 'leaderboard/results.json').read_text())
    for policy in index['policies']:
        source = policy['source']
        if policy['policy_id'] in known or source['repository'] != 'zapatacomputing/forshor-submissions':
            continue
        number = str(source.get('pr_number', ''))
        if not number.isdigit():
            raise ValueError('Accepted private submission has no PR evidence')
        pr = request_json(f'https://api.github.com/repos/zapatacomputing/forshor-submissions/pulls/{number}', os.environ['GH_TOKEN'])
        attribution.append({'submissionId': policy['policy_id'], 'headSha': policy['policy_id'],
                            'githubLogin': pr['user']['login'], 'evidenceUrl': pr['html_url']})
    return state


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    metadata = json.loads(Path('evaluation-metadata.json').read_text())
    url = os.environ['PUBLISHER_URL'].rstrip('/')
    token = os.environ['PUBLISHER_TOKEN']
    if args.check:
        state = request_json(url + '/state', token)
        completed = state.get('completedEvaluations', {}).get(metadata['evaluationKey'])
        if completed and (completed['headSha'] != metadata['headSha'] or completed['runId'] != metadata['runId']):
            raise ValueError('Evaluation identity collision')
        with open(os.environ['GITHUB_OUTPUT'], 'a') as output:
            output.write(f"complete={'true' if completed else 'false'}\n")
        if completed:
            result = {'alreadyPublished': True, 'evaluationKey': metadata['evaluationKey']}
            Path('publication-result.json').write_text(json.dumps(result))
            with open(os.environ['GITHUB_STEP_SUMMARY'], 'a') as summary:
                summary.write('\n## Already published\n\nNo dependency restore, resource estimation or website write was repeated.\n')
        raise SystemExit(0)
    from estimate import generate
    result = publish_with_recovery(metadata,
        lambda: request_json(url + '/state', token),
        lambda: refresh_archive(Path('archive')),
        lambda archive, state, evaluation: generate(archive, add_missing_attribution(archive, state), evaluation),
        lambda payload: request_json(url + '/publish', token, payload))
    print(json.dumps(result))
    Path('publication-result.json').write_text(json.dumps(result))
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'], 'a') as summary:
            summary.write('\n## Results publication\n\n' + (
                'This evaluation is already published; no estimation or website write was repeated.\n'
                if result.get('alreadyPublished') else f"Published snapshot `{result['snapshotId']}`.\n"))
