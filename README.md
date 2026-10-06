# wsi-mil-demo

A device-style demo of slide-level analysis of gigapixel whole-slide images
using a pretrained multiple instance learning (MIL) model.

> Research demo only. Not for clinical use.

## Components
- `services/inference/` - Python inference service (the "device")
- `apps/web/` - Node.js web app

## Documentation
- [Architecture](docs/architecture.md)
- [API contract](docs/api-contract.md)
- [Requirements](docs/requirements.md)
- [Risk register](docs/risk-register.md)
- [SOUP inventory](docs/soup.md)
- [Decision log](docs/decisions.md)
- [Roadmap](docs/roadmap.md)

## Running
Setup instructions are added as each component is built.

## License
MIT. Third-party components, models, and data carry their own licenses;
see `docs/soup.md`.
