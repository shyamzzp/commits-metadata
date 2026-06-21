from app.github.rate_limiter import RateLimiter


class TestRateLimiter:
    def test_update_from_headers(self):
        rl = RateLimiter()
        state = rl.update_from_headers(
            {"X-RateLimit-Limit": "5000", "X-RateLimit-Remaining": "10", "X-RateLimit-Reset": "1700000000"}
        )
        assert state.limit == 5000
        assert state.remaining == 10
        assert state.reset_epoch == 1700000000

    def test_should_throttle_when_exhausted(self):
        rl = RateLimiter()
        rl.update_from_headers({"X-RateLimit-Remaining": "0"})
        assert rl.should_throttle() is True

    def test_no_throttle_when_plenty(self):
        rl = RateLimiter()
        rl.update_from_headers({"X-RateLimit-Remaining": "4999"})
        assert rl.should_throttle() is False

    def test_seconds_until_reset(self):
        rl = RateLimiter()
        rl.update_from_headers({"X-RateLimit-Reset": "100"})
        assert rl.seconds_until_reset(now_epoch=40) == 60
        assert rl.seconds_until_reset(now_epoch=200) == 0

    def test_detects_hard_rate_limit_response(self):
        rl = RateLimiter()
        assert rl.is_rate_limited_response(403, {"X-RateLimit-Remaining": "0"}) is True
        assert rl.is_rate_limited_response(403, {"X-RateLimit-Remaining": "5"}) is False
        assert rl.is_rate_limited_response(200, {"X-RateLimit-Remaining": "0"}) is False

    def test_missing_headers_are_safe(self):
        rl = RateLimiter()
        rl.update_from_headers({})
        assert rl.should_throttle() is False
        assert rl.seconds_until_reset(now_epoch=0) == 0
