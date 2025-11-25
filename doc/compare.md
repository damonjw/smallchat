The current architecture of this codebase is summarized in @V1.md. I'm planning a new design,
described in the folder v2.

First, review the goals in @v2/GOALS.md. 
Next, review the architecture in @v2/PLAN.md. Does the plan live up to the goals? Are there ways to improve
the plan to better meet the goals? For each issue you identify, 
consider the issue using a subagent.
- The subagent should follow the general instructions in CLAUDE.md.
- It should consider the issue from both sides. It shouldn't be satisfied with vague vibes or feels:
  it must come up with specific concrete issues. For example, don't just say "This looks more complex",
  actually try it and see if it is more complex.
- It should also look in the plan to see if it has any comments about that issue. 
  And evaluate such comments. It might or might not agree with them. Its job is to
  provide a fair evaluation, not to blindly agree with the plan, nor to disagree with the plan just for the sake of argument.

You should also evaluate the conclusions from each subagent yourself, following the same principles.

---

The current architecture of this codebase is summarized in @V1.md. I'm planning a new design,
described in the folder v2. Review the goals in @v2/GOALS.md. Are there goals that are inherently
flawed?
