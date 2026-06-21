from app.jobqueue.job_queue import CommitJob, CommitQueue


class TestCommitQueue:
    def test_enqueue_and_drain(self):
        q = CommitQueue()
        q.enqueue_many([CommitJob("o", "r", "a"), CommitJob("o", "r", "b")])
        assert q.pending == 2
        assert q.next_job().sha == "a"
        assert q.next_job().sha == "b"
        assert q.next_job() is None

    def test_failure_routes_to_retry_until_max(self):
        q = CommitQueue(max_retries=2)
        job = CommitJob("o", "r", "a")
        assert q.mark_failed(job, "boom") == "retry"   # attempt 1
        assert q.mark_failed(job, "boom") == "retry"   # attempt 2
        assert q.mark_failed(job, "boom") == "dead_letter"  # attempt 3 > max
        assert len(q.dead_letters) == 1
        assert q.dead_letters[0].last_error == "boom"

    def test_retry_drained_before_main(self):
        q = CommitQueue()
        q.enqueue(CommitJob("o", "r", "main"))
        retry_job = CommitJob("o", "r", "retry")
        q.mark_failed(retry_job, "x")
        assert q.next_job().sha == "retry"
        assert q.next_job().sha == "main"

    def test_stats_and_empty(self):
        q = CommitQueue()
        assert q.is_empty()
        q.enqueue(CommitJob("o", "r", "a"))
        assert q.stats()["main"] == 1
        assert not q.is_empty()

    def test_repository_property(self):
        assert CommitJob("octocat", "hello", "a").repository == "octocat/hello"
