import json
from datetime import UTC, datetime, timedelta
from functools import wraps
from typing import Any, ParamSpec, Protocol, TypeVar
from urllib.request import urlopen

INVALID_CRITICAL_COUNT = "Breaker count must be positive integer!"
INVALID_RECOVERY_TIME = "Breaker recovery time must be positive integer!"
VALIDATIONS_FAILED = "Invalid decorator args."
TOO_MUCH = "Too much requests, just wait."


P = ParamSpec("P")
R_co = TypeVar("R_co", covariant=True)


class CallableWithMeta(Protocol[P, R_co]):
    __name__: str
    __module__: str

    def __call__(self, *args: P.args, **kwargs: P.kwargs) -> R_co: ...


class BreakerError(Exception):
    def __init__(self, func_name: str, block_time: datetime):
        self.func_name = func_name
        self.block_time = block_time
        super().__init__("Too much requests, just wait.")


def _check_critical_count(critical_count: int, errors: list[Exception]) -> None:
    if not isinstance(critical_count, int) or critical_count <= 0:
        errors.append(ValueError(INVALID_CRITICAL_COUNT))


def _check_time_to_recover(time_to_recover: int, errors: list[Exception]) -> None:
    if not isinstance(time_to_recover, int) or time_to_recover <= 0:
        errors.append(ValueError(INVALID_RECOVERY_TIME))


class CircuitBreaker:
    def __init__(
        self,
        critical_count: int = 5,
        time_to_recover: int = 30,
        triggers_on: type[Exception] = Exception,
    ):
        errors: list[Exception] = []

        _check_critical_count(critical_count, errors)
        _check_time_to_recover(time_to_recover, errors)

        if errors:
            raise ExceptionGroup(VALIDATIONS_FAILED, errors)

        self._critical_count = critical_count
        self._time_to_recover = time_to_recover
        self._triggers_on = triggers_on

        self._number_rejections: int = 0
        self._blocked: bool = False
        self._blocked_time: datetime

    def __call__(self, func: CallableWithMeta[P, R_co]) -> CallableWithMeta[P, R_co]:
        @wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R_co:
            self._block(func)
            try:
                ans = func(*args, **kwargs)
            except self._triggers_on as error:
                self._number_rejections += 1

                if self._number_rejections == self._critical_count:
                    self._blocked = True
                    self._blocked_time = datetime.now(UTC)

                    full_name = f"{func.__module__}.{func.__name__}"
                    raise BreakerError(full_name, self._blocked_time) from error
                raise

            self._number_rejections = 0
            return ans

        return wrapper

    def _block(self, func: CallableWithMeta[P, R_co]) -> None:
        if self._blocked:
            blocked_until = self._blocked_time + timedelta(seconds=self._time_to_recover)

            if blocked_until > datetime.now(UTC):
                full_name = f"{func.__module__}.{func.__name__}"
                raise BreakerError(full_name, self._blocked_time)
            self._blocked = False
            self._critical_count = 0


circuit_breaker = CircuitBreaker(5, 30, Exception)


# @circuit_breaker
def get_comments(post_id: int) -> Any:
    """
    Получает комментарии к посту

    Args:
        post_id (int): Идентификатор поста

    Returns:
        list[dict[int | str]]: Список комментариев
    """
    response = urlopen(f"https://jsonplaceholder.typicode.com/comments?postId={post_id}")
    return json.loads(response.read())


if __name__ == "__main__":
    comments = get_comments(1)
