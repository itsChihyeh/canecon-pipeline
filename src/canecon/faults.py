"""Fault injection for demos and tests.

FaultInjectingTransport sits in front of a real (or recorded) transport and answers
some requests with an injected failure instead of passing them on. Rules match a
keyword in the request URL:

    valet=500,500        the first two Bank of Canada requests get HTTP 500, then real
    getSeriesInfo=503*   every series-info request gets HTTP 503 (never recovers)
    statcan=timeout      the first StatCan request times out

Nothing here is used unless a fault rule is given explicitly.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import httpx


@dataclass
class FaultRule:
    keyword: str
    faults: list[str]  # "500", "503", "timeout", ...
    forever: bool = False
    used: int = 0

    def next_fault(self) -> str | None:
        if self.forever:
            self.used += 1
            return self.faults[0]
        if self.used < len(self.faults):
            fault = self.faults[self.used]
            self.used += 1
            return fault
        return None


def parse_rule(spec: str) -> FaultRule:
    """'valet=500,500' -> FaultRule('valet', ['500', '500']); '503*' means forever."""
    keyword, sep, rest = spec.partition("=")
    if not sep or not keyword or not rest:
        raise ValueError(f"bad fault rule {spec!r}; expected KEYWORD=FAULT[,FAULT...] or KEYWORD=FAULT*")
    forever = rest.endswith("*")
    faults = rest.rstrip("*").split(",")
    for f in faults:
        if f != "timeout" and not (f.isdigit() and 400 <= int(f) <= 599):
            raise ValueError(f"bad fault {f!r} in {spec!r}; use an HTTP status 400-599 or 'timeout'")
    if forever and len(faults) != 1:
        raise ValueError(f"'*' takes a single fault: {spec!r}")
    return FaultRule(keyword, faults, forever)


class FaultInjectingTransport(httpx.BaseTransport):
    def __init__(
        self,
        inner: httpx.BaseTransport,
        rules: list[FaultRule],
        on_fault: Callable[[str, str], None] | None = None,
    ):
        self.inner = inner
        self.rules = rules
        self.on_fault = on_fault
        self.log: list[tuple[str, str]] = []  # (rule keyword, injected fault)

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        for rule in self.rules:
            if rule.keyword in url:
                fault = rule.next_fault()
                if fault is None:
                    break
                self.log.append((rule.keyword, fault))
                if self.on_fault:
                    self.on_fault(rule.keyword, fault)
                if fault == "timeout":
                    raise httpx.ConnectTimeout(f"injected timeout for {rule.keyword}", request=request)
                return httpx.Response(int(fault), content=b"injected fault", request=request)
        return self.inner.handle_request(request)

    def close(self) -> None:
        self.inner.close()
