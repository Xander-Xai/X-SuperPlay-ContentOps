# Audited X post corpus (this thread, 2026-11-12)

This is **not** a verified database of top-performing X posts. The user reports high impressions and interactions but has not provided individual post URLs or first-party metrics. The following 10 visible inputs (plus one summary-only earlier turn) are traceable to the current conversation, and **none of the assistant-written replies are treated as high-performing source posts**.

| ID | Input summarized without copying complete third-party text | Pattern | Safety / evidentiary constraint |
|---|---|---|---|
| S01 | 英伟达CEO更替及指定继任者的未经核实传闻 | P01 | HOLD_FACT_CHECK |
| S02 | 晨雾、蓝色冰湖、金色光束的短景物描写 | P02 | PASS_WITH_RIGHTS_REVIEW |
| S03 | 英文要求回复特定关键词以获得数千关注者 | P03 | NEGATIVE_EXAMPLE |
| S04 | 网购衣物卫生担忧并建议先洗再穿 | P04 | PASS_WITH_CAVEAT |
| S05 | 声称平台给流量时一张白纸也可破万浏览 | P05 | HYPOTHESIS_ONLY |
| S06 | 短暂出现后404的iOS终端仓库及所谓沙盒逃逸技术帖 | P06 | HOLD_FACT_CHECK |
| S07 | 第二条英伟达董事会罢免CEO的高紧迫性核实请求 | P01 | HOLD_FACT_CHECK |
| S08 | 冬夜热馄饨，邀请X友一起吃 | P02 | PASS_WITH_RIGHTS_REVIEW |
| S09 | 先列举多个肾病误区，再通过显示更多制造反转 | P08 | HOLD_MEDICAL_REVIEW |
| S10 | 长年使用Claude和代理工具未封号的幸存者经历 | P07 | HYPOTHESIS_ONLY |
| S11 (summary-only) | Robotaxi一周168小时的AI与工作时长对比短句 | P09 | SUMMARY_ONLY |

## Supported conclusions

- TEXT OBSERVED: These 10 visible user inputs use attention hooks, concrete scenes, identity/ingroup signals, fear/disgust, debate invitation, technical curiosity and/or narrative suspense. Two Nvidia posts concern the **same rumor**; they are separate text samples, not two factual confirmations.
- SUMMARY ONLY: S11 came from a prior-turn summary and is deliberately outside the 10 literal inputs directly visible here.
- USER-REPORTED: The user says the originals have been validated by platform data; **the measurements, post identities, and observation windows were not provided here**.
- NOT SUPPORTED: a ranking of which hook outperformed another, causal effect, a predicted view count, a proven growth formula, or a proof that any response written by the assistant was published successfully.
- NEGATIVE EXAMPLE: S03 uses a 'type keyword -> guaranteed followers' lure. Analyze its short CTA syntax but do not reproduce its deceptive reward bargain.
- The ledger contains paraphrases, not source text suitable for reposting. Original writing requires a new scene, substantive thought and audience fit.

## Atomic writing mechanisms

| Pattern ID | Text mechanism observed | Safe derivative idea | Why this is only a hypothesis |
|---|---|---|---|
| P01 | famous name + purported authority + extreme uncertainty + demand for verification | verified-fact-versus-rumor analysis | no official confirmation or performance metrics in pasted samples |
| P02 | 2–3 sensory details + atmospheric image / warmth + simple shared feeling | authentic photo with short lived detail and optional grounded question | image and posting data absent |
| P03 | extremely low entry cost + huge reward promise | **never promise followers**; replace with genuine reader value | manipulative mechanics and unsupported outcome |
| P04 | shock/disgust + simple protective action | specific practical observation with careful qualification | the unseen photo/background may change accuracy |
| P05 | bold counterfactual 'even a blank page could...' + playful challenge | challenge a platform assumption without declaring algorithm truth | unsupported platform mechanism and sample outcome |
| P06 | 'vanished repository' + surprising capability + cliffhanger | verified mechanism, caveat and a real technical question | repository status/technical claim is not established by the pasted text |
| P07 | unexpected personal survival anecdote + implied rule reversal | observational counterexample + explicit survivorship bias | anecdote does not establish platform policy |
| P08 | numbered debunking list + 'what actually matters is...' curiosity gap | medically accurate myth/fact explainer with cited caveats | medical uncertainty; avoid implying a diagnosis |
| P09 | short, numerical human/machine contrast | arithmetic-grounded humor distinguishing ideal vs actual | observed only in summarized earlier message |

## Outcomes contract

Use the code-readable [sample-ledger.json](sample-ledger.json) as the single source of sample IDs, risk marks and pattern links. No sample's `observed_metrics` can be filled without first-party, date-stamped observations and a real X URL. Real post performance is tracked separately in the existing project CSVs, not this static training ledger.
