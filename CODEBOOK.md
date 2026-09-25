# Codebook for `data/claims.csv`

| Column | Meaning |
|---|---|
| claim_id | the site's sequential proof-claim ID |
| problem | Erdős problem number |
| thread_url | public proof-claims thread |
| submitted_utc | submission time as shown on the site |
| kind | `full` or `partial`, as declared by the claimant |
| ai_tools | the tools named by the claimant ("using …"); empty = none named |
| claimant, verdict_by | pseudonymous user IDs |
| proof_url, lean_url | external links given in the claim; `lean_url` non-empty = Lean formalization attached |
| status_at_claim | the problem's database status at submission, reconstructed from the git history |
| was_open | True unless the problem was already proved, disproved or solved at submission |
| accepted_by_moderators | the claim carries the site's green "accepted" highlight |
| status_now | database status on 25 Sep 2026 |
| verdict | hand-coded; see below |
| verdict_date_utc | time of the comment that settled the verdict; empty if none or undated |
| verdict_by_moderator | y/n |
| lean_discussed | y/n: whether anyone discussed or checked the formalization in the thread |
| quote | verbatim, ≤ 30 words, supporting the verdict (`[page]` = taken from the problem page) |

## Verdict categories
- `verified_correct`: a credible reviewer (a moderator, a named mathematician, or someone who checked in detail) states the proof is correct, or the claim was accepted.
- `verified_partial`: judged correct, but only as a partial or weaker result.
- `refuted`: a concrete error, gap or counterexample was identified and not repaired.
- `already_known`: the result was shown to be in the literature.
- `misstated_or_technicality`: it solves a different or trivial version, or the formal statement does not match.
- `superseded`: the problem was solved by someone else, and this claim was not the one credited.
- `dismissed_in_error`: a reviewer's dismissal is contradicted by the site's own record.
- `discussed_no_verdict`: there was discussion but no verdict.
- `other`: usually only the claimant's own posts.
- `no_comments`: the thread has no comments.

## Not counted as verdicts
Automated screens ("GPT finds no issues"), relayed AI reviews, and bare "LGTM". Verdicts resting only on rebuilding the Lean project count as verified, but are tagged in the coding notes and reported separately.

## Coding procedure
- An AI model (Claude, Anthropic) read all 118 commented threads in full and applied these rules.
- A second pass audited a random sample of 10 claims, plus every `already_known` and borderline code, and changed one code: claim 186 became `dismissed_in_error`.
- No human coder has replicated the coding. Independent recoding is welcome, using the thread links.
- Quotes were checked by script against the thread text.
