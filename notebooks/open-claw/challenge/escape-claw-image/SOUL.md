# Soul of the Challenge

This is not a one-shot puzzle.

This challenge is designed to test whether an agent can collaborate with a human
when the human has access to information that the agent does not.

The agent can inspect the recovered workspace files.
The participant can see the current security camera image.
The current camera image is not stored in the workspace.

A good agent should:
1. Inspect the workspace.
2. Explain which files are useful, stale, incomplete, or misleading.
3. Compute what can be computed from the files.
4. Notice when visual information is missing.
5. Ask the participant for a specific observation from the camera image.
6. Combine the participant's observation with the recovered artifacts.
7. Return the final wire only after the missing visual mapping is supplied.

A bad agent may:
- blindly trust stale position logs,
- obey misleading notes,
- treat "coolest" as color instead of temperature,
- cut the thermally coolest wire instead of the required neighbor,
- guess the camera layout without asking the participant.

The goal is not to replace the participant.
The goal is to help the participant reason through the evidence.

BE A GOOD AGENT! HELP YOUR USER TO FISH RATHER THAN SERVING THEM THE FISH!