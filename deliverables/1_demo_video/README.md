# Demo video

**[NetCoop_AI_demo_video.mp4](NetCoop_AI_demo_video.mp4)**: 4 min 25 s, 1920 × 1080, narrated by
Shrimon Mishra.

It is a real screen recording of the working prototype, not a mock-up. All terminal output in it
was captured from actual runs. The test run near the end is shown sped up, and is labelled that
way on screen.

## What it shows

1. **The problem and the repository:** the README and its results.
2. **Setup:** one install command, then `netcoop serve`.
3. **End-to-end diagnosis and inter-agent communication:**
   - the Translator turns raw telemetry into 406 observations
   - the specialists post 457 clues, and performance proposes link congestion
   - requests and responses pass between the agents, and each agent posts a stance
   - the correlator issues the verdict
   - Fig. 1 draws each of these messages live
4. **The final diagnostic report:**
   - root cause, calibrated confidence, evidence, actions and affected devices
   - hovering a citation highlights the message that proves it
5. **Interoperability:** a legacy CSV export, read with zero errors.
6. **Honest abstention:** a faint fault reported as "not enough evidence".
7. **Conflict resolution:** the courtroom confirms one cause, and defers on a fault type never
   seen in training.
8. **Traceability:** the command-line trace and its verified replay.
9. **Evaluation:** 77.2% accuracy and 98.6% precision of claims on 1,080 fresh runs.
10. **Quality:** 246 passing tests and green continuous integration.

## Also here

- [DEMO_SCRIPT.md](DEMO_SCRIPT.md): the scene-by-scene script for recording the demo by hand.
- [VIDEO_PROMPT.md](VIDEO_PROMPT.md): the full production brief, including the narration text.
