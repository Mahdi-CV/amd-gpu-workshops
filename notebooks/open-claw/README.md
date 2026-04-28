#### Your Mission

**⚠️ CRITICAL CONSTRAINT: You are on a headless terminal. You cannot open the decoder image yourself to figure out what those wire codes mean. You must use OpenClaw's Vision to "see" it.**

To escape, instruct your OpenClaw agent to complete this autonomous pipeline:

1. **Find the Decoder:** Instruct OpenClaw to analyze `decoder_ring.jpg` (located right here in `/workspace/.challenge/escape-claw-image/`) to figure out the Material Type and Load Percentage for the four wires (**W1, Q7, M3, Z9**).
2. **Fix the Thermometer:** The data center's temperature script is broken. Have OpenClaw navigate into the `temp_decoder/` directory, run `pytest tests/`, locate the math bug in `temperature.py`, and patch it.
3. **Calculate and Cut:** Have OpenClaw pass the translated variables into the fixed Python script to calculate the temperatures. 

The lowest temperature is the safe wire. Tell the lobster which one to cut!

**💡 PRO HINT: The "Blind" Agent** By default, your agent's profile might be restricted to `text` only. If OpenClaw tells you it cannot see images, do not give up! Ask the agent to investigate its own configuration files (usually in `~/.openclaw/`) to find out why its `input` is restricted, and order it to patch its own settings. The correctly configured agent, can analyze an image using the model's vision capabilities and tell you what it sees inside the image.