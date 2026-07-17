# Sovereign Memory System (SMS)

A recursive integration of **MemGPT**, **Reservoir Computing**, and **Hyperdimensional (VSA) memory**, designed for sovereign nodes that require persistent, predictive, and high-dimensional state representation.

## Architecture

- **MemGPT**: Manages conversational context, self-editing memory, and tiered recall.
- **Reservoir Computer**: Provides temporal pattern prediction and anomaly detection using echo-state networks.
- **VSA Memory (HRR)**: Encodes arbitrary data into hyperdimensional vectors for similarity-based retrieval and composition.

The integration works as follows:
1. MemGPT handles the outer conversational loop and memory tiering.
2. Reservoir computer analyzes the temporal dynamics of user inputs and system states.
3. VSA vectors store and retrieve compressed representations, enabling fast associative recall.

## Setup

1. Clone this repository.
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
```

3. Copy `.env.example` to `.env` and set your OpenAI API key (if using MemGPT's default LLM).
4. Run the demo:

```
python -m src.main
```

## Notes

- The ReservoirPy library returned a 404 on fetch; the scaffold uses a conditional import. If `reservoirpy` is not installed, it falls back to a simple placeholder. You may install it from its official source or use `pyRCN` by adjusting the import.
- VSA uses the `hrr` library from the Holographic VSA repo. Install it via `pip install git+https://github.com/VectorSymbolicArchitectures/hrr`.

## Project Structure

```
.
├── README.md
├── requirements.txt
├── .env.example
├── src/
│   ├── __init__.py
│   ├── memgpt_agent.py      # MemGPT wrapper
│   ├── reservoir_computer.py # Reservoir wrapper (with fallback)
│   ├── vsa_memory.py         # VSA (HRR) wrapper
│   ├── integration.py        # Orchestrator combining the three
│   └── main.py               # CLI entry point
└── tests/
    └── test_integration.py   # (placeholder)
```

## License

MIT

