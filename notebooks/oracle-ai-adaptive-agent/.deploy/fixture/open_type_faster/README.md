# Open Type Faster

Terminal typing trainer. Tracks WPM, accuracy, and suggests words to practice.

## Setup

```bash
pip install -r requirements.txt
```

## Run

```bash
python3 main.py                          # 25-word test (default)
python3 main.py --words 50               # custom word count
python3 main.py --time 60                # 60-second timed test
python3 main.py --difficulty hard        # easy | medium | hard | mixed
python3 main.py --mode practice          # focus on your weak words
python3 main.py history                  # last 10 sessions
python3 main.py stats                    # all-time stats
```

## Tests

```bash
python3 -m pytest tests/
```
