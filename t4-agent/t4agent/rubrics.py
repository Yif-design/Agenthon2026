from __future__ import annotations


def select_rubric(family: str, target_name: str, prompt: str) -> str:
    text = f"{family} {target_name} {prompt}".lower()
    if "credit" in text:
        return (
            "Credit-event rubric: weigh liquidity, debt maturities, covenant waivers, missed payments, "
            "going-concern language, bankruptcy language, rating actions, and refinancing access. "
            "Do not treat a waiver or risk disclosure as an event unless it supports the forecast."
        )
    if "eps" in text:
        return (
            "EPS rubric: compare revenue, margins, expenses, guidance, share count, tax/one-time items, "
            "and prior-year EPS. EPS direction can differ from revenue direction."
        )
    if "yield" in text or "curve" in text:
        return (
            "Rates rubric: short maturities follow expected policy path; long maturities also reflect growth, "
            "inflation expectations, and term premium. Use FOMC language and pre-cutoff curve levels."
        )
    if "cpi" in text:
        return (
            "CPI rubric: forecast the named component in stated units. Use component-specific evidence; "
            "headline CPI evidence alone may not support a component forecast."
        )
    if "auction" in text:
        return (
            "Auction rubric: bid-to-cover depends on offering size, reopening/new issue, rate level, demand, "
            "and recent auction tone. Forecast the ratio, not a probability."
        )
    if "position" in text or "cot" in text:
        return (
            "Positioning rubric: forecast change in net positioning as a share of open interest. "
            "Use prior net position, recent change, asset class context, and COT evidence."
        )
    if "revision" in text:
        return (
            "Macro revision rubric: compare latest pre-cutoff estimate with agency context and related series. "
            "Forecast next revision direction only, not the final level."
        )
    if "reaction" in text:
        return (
            "Post-earnings reaction rubric: predict abnormal return direction around the release. "
            "Use expectations, valuation-sensitive guidance, revenue, margins, and known pre-release setup."
        )
    return (
        "Generic tabular prediction rubric: use only the provided row facts and frozen evidence. "
        "Match the target units, prefer conservative intervals, and cite evidence that directly supports the prediction."
    )
