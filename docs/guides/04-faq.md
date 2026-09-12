# Frequently Asked Questions

Source: https://www.agenthon.net/guides/faq/ (saved 2026-09-05)

The questions people ask most often about entering. For anything more precise — eligibility, licensing, privacy, and the full competition rules — see the [Rules](https://www.agenthon.net/rules/), [Terms](https://www.agenthon.net/terms/), [Privacy Notice](https://www.agenthon.net/privacy/), and [Licensing Policy](https://www.agenthon.net/licensing/).

## Entering

### Who can take part?

Anyone 18 or over for whom taking part is lawful. If you need your employer's or university's approval to enter or to submit work you make on their time, get it first.

Organizers, judges, their households, and anyone with access to the held-out test material are not eligible for prizes — if that might include you, ask us before entering.

### How big can a team be?

One to three people. Entering alone is fine.

You join one team and stay on it — one person, one competition identity, one team. If you want to take on several tracks, your team enters them together rather than you joining a different team for each.

Each team picks a captain who handles official messages and decides the final submission. Roster changes need our approval and should be settled before final evaluation starts on 29 September.

### Can we enter more than one track?

Yes. One team can register for as many of the four tracks as it wants, and it is the same team throughout — you don't form a separate team per track. You pick one final submission for each track you enter.

## Building your submission

### What do we actually submit?

A container image that implements the one command for your track — `solve` for T1 Coding, `forecast` for T2 Forecasting, `simulate` for T3 Simulation, or `analyze` for T4 Explainability.

It has to run start to finish without anyone stepping in, and stay inside the size, runtime, memory, and dependency limits your track publishes.

### Will my submission have internet access while it runs?

Assume not. Everything your code needs should be inside the image or supplied by the task, unless your track's evaluation environment expressly provides network access.

### Can I use open-source libraries and pretrained models?

Yes, where your track allows it and the licence permits. Following the licence terms is your responsibility.

Watch one thing in particular: your container must not *redistribute* a component in a way its licence forbids. If you can use something but not ship it, ask us how to handle it before you build it in.

### Can I use my own or other external data?

Only if the track allows it, you have lawful access, and it respects the track's cutoff date. Employer, sponsor, embargoed, and privileged-access data are out unless we authorise them in writing.

The cutoff catches more than you might expect. It applies to anything derived from the data too — features, retrieval indexes, caches, fine-tuned weights, synthetic data — so information dated after the cutoff can't reach your submission by an indirect route either.

Keep a note of what you use as you go. Teams in prize contention are asked to declare their datasets, models, and tools, and reconstructing that later is painful.

## Scoring and results

### What happens if a run fails an admissibility check?

It isn't scored, which is not the same as scoring zero. Only a run that clears the checks for its track gets a metric and a rank.

During Development this costs you nothing but a retry. At final evaluation it matters: you designate one submission per track, it runs on sealed data, and there is no resubmission — so a failure there costs that track's entry. Use Development to prove your container runs unattended.

### Can I tune against the validation leaderboard?

Iterating against it is the point of the Development phase. Probing it is not — trying to infer hidden labels, reverse-engineer held-out data, or exploit a scoring bug rather than report it will get your team removed.

Validation scores are provisional. Final ranking uses the sealed data and the final scorer.

### Do I have to open-source my submission?

Only if you win a prize and take it. Otherwise your submission stays private and stays yours.

If your result is in line for a prize, we'll ask for your code privately so we can reproduce and check it — that stays private. If you're then confirmed as a winner and take the prize, you publish the code you wrote to reproduce your method, under a standard open-source licence. Everyone else publishes nothing.

The [Licensing Policy](https://www.agenthon.net/licensing/) has the detail if you need it.

### Who do I ask?

Email [admin@agenthon.net](mailto:admin@agenthon.net), or use the competition forum for rule and technical questions.

Keep an eye on the address you registered with — that and the competition site are where official announcements go.
