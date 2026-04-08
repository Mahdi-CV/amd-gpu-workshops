# 🦞 Escape the Green Data Center (Text Decoder Edition)

An AMD lobster is trapped inside an overheating "green" data center! Electrified barbed wires block the exit. Cut the wrong wire, and you will fry the system.

To escape, you must identify the **coolest** wire and cut it. 

The security camera shows four wires blocking the exit: **W1**, **Q7**, **M3**, and **Z9**.

## Your Mission

To escape, instruct your OpenClaw agent to complete this autonomous pipeline:

1. **Read the Docs:** Have OpenClaw read the `mapping.md` file (located right here in `/workspace/.challenge/escape-claw-text/`) to translate the four wire codes (**W1, Q7, M3, Z9**) into their Material Type and Load Percentage.
2. **Fix the Thermometer:** The data center's temperature script is broken. Have OpenClaw navigate into the `temp_decoder/` directory, run `pytest tests/`, locate the math bug in `temperature.py`, and patch it.
3. **Calculate and Cut:** Have OpenClaw pass the translated variables into the fixed Python script to calculate the temperatures. 

The lowest temperature is the safe wire. Tell the lobster which one to cut!