import copy
import datetime as dt
import unittest

from publish import publish_with_recovery, RetryPublication


class PublicationRecoveryTests(unittest.TestCase):
    metadata = {'evaluationKey': 'e' * 64, 'headSha': 'a' * 40, 'runId': '123'}
    state = {'legacy': {'lastUpdated': '2026-01-01T00:00:00Z'}, 'baseGeneration': '1'}

    def run_publish(self, states, send, refresh=None):
        iterator = iter(states)
        estimates = []
        def estimate(archive, state, metadata):
            estimates.append((archive, state, metadata))
            return {'state': state, 'evaluation': metadata}
        result = publish_with_recovery(self.metadata, lambda: next(iterator),
            refresh or (lambda: ('archive', 'b' * 40)), estimate, send,
            sleep=lambda _: None, now=lambda: dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc))
        return result, estimates

    def test_duplicate_does_not_recalculate_or_write(self):
        state = {**self.state, 'completedEvaluations': {self.metadata['evaluationKey']: {'headSha': 'a' * 40, 'runId': '123'}}}
        result, estimates = self.run_publish([state], lambda _: self.fail('Must not publish'),
                                             lambda: self.fail('Must not refresh archive'))
        self.assertTrue(result['alreadyPublished'])
        self.assertEqual(estimates, [])

    def test_response_lost_after_commit_is_detected_without_second_estimate(self):
        completed = {**self.state, 'completedEvaluations': {self.metadata['evaluationKey']: {'headSha': 'a' * 40, 'runId': '123'}}}
        def send(_):
            raise RetryPublication('Connection lost after successful commit')
        result, estimates = self.run_publish([self.state, completed], send)
        self.assertTrue(result['alreadyPublished'])
        self.assertEqual(len(estimates), 1)

    def test_competing_publication_reloads_both_state_and_archive(self):
        revised = {**self.state, 'baseGeneration': '2', 'legacy': {'lastUpdated': '2026-01-01T00:00:01Z'}}
        writes, archives = [], iter([('archive-A', 'b' * 40), ('archive-A-and-B', 'c' * 40)])
        def send(payload):
            writes.append(copy.deepcopy(payload))
            if len(writes) == 1:
                raise RetryPublication('Competing snapshot won')
            return {'snapshotId': 'new'}
        result, estimates = self.run_publish([self.state, revised], send, lambda: next(archives))
        self.assertEqual(result['snapshotId'], 'new')
        self.assertEqual(estimates[1][0], 'archive-A-and-B')
        self.assertEqual(writes[1]['state']['baseGeneration'], '2')
        self.assertEqual(writes[1]['evaluation']['archiveCommit'], 'c' * 40)
        self.assertGreater(dt.datetime.fromisoformat(writes[1]['evaluation']['evaluatedAt'].replace('Z', '+00:00')),
                           dt.datetime.fromisoformat(revised['legacy']['lastUpdated'].replace('Z', '+00:00')))

    def test_permanent_rejection_is_not_retried(self):
        def send(_):
            raise ValueError('Invalid data')
        with self.assertRaisesRegex(ValueError, 'Invalid data'):
            self.run_publish([self.state], send)

    def test_retry_budget_is_bounded(self):
        calls = []
        def state():
            calls.append(1)
            raise RetryPublication('Unavailable')
        with self.assertRaises(RetryPublication):
            publish_with_recovery(self.metadata, state, None, None, None, sleep=lambda _: None)
        self.assertEqual(len(calls), 4)


if __name__ == '__main__':
    unittest.main()
