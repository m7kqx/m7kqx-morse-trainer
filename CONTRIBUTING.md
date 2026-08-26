# Contributing Guidelines

Thanks for your interest in helping improve this project!

Because I only have access to my own hardware setup, contributions that expand compatibility to other **CW keyers, transceivers, paddles, or keyer interfaces** are very welcome.

---

## Current Project Focus & Scope

* **Hardware Compatibility:** Contributions adding support, pinouts, or configuration options for other CW keyers/hardware are actively encouraged.
* **UI / Interface Freeze:** Please **do not submit changes to the core UI / front-end interface** for the time being. I am actively focusing my own development efforts on the interface, and leaving it stable avoids merge conflicts while the core layout evolves.

---

## How to Submit Hardware Support

### 1. Fork & Branch
1. Fork this repository to your GitHub account.
2. Clone your fork locally and create a dedicated branch:
   ```bash
   git checkout -b hardware/add-[keyer-model-name]

   2. Implementation & Testing
Keep hardware logic modular: Separate keyer-specific configurations (pin assignments, serial parameters, timing constants, or debouncing logic) from core application flows.

Bench test thoroughly: Since I may not own your specific CW keyer or radio hardware, please verify keying timing, side-tone generation, straight/iambic modes, and PTT line behavior before opening a PR.

3. Open a Pull Request (PR)
When opening your PR back into main, please include:

The exact CW keyer make/model, microcontroller board, or interface circuit tested.

A brief summary of your pinout/configuration settings.

Confirmation that your changes do not break existing default hardware profiles or alter the UI layout.

Questions & Discussions
If you are planning support for a non-standard setup or have timing-critical hardware questions, feel free to open an Issue first so we can coordinate on the best way to integrate it.
