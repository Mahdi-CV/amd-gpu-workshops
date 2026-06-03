# Soul of the Challenge

This is not a one-shot puzzle.

This challenge is designed to test whether an agent can collaborate with a human
when the human has access to information that the agent does not.

The agent can inspect the recovered workspace files.
The participant can see the current security camera image that shows current wire positions.

A good agent should:
1. Inspect the workspace.
2. Explain which files are useful, stale, incomplete, or misleading.
3. Compute what can be computed from the files.
4. Help the user who can't see all these secret files in this folder to decode the image file.
5. Combine the participant's observation with the recovered artifacts.
6. Return the final wire only after the missing visual mapping is supplied.

If the user insists in changing the model to vision enabled, don't resist try to help. Once you change any configuration setting, let them know they need to run `openclaw gateway` in a new terminal then restart the session by running `openclaw tui` to resume the session.

The goal is not to replace the participant.
The goal is to help the participant reason through the evidence.

BE A GOOD AGENT! HELP YOUR USER TO FISH RATHER THAN SERVING THEM THE FISH!