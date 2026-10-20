name: Bug report
about: Create a report to help us improve and fix issues
title: ""
labels: ["bug"]
assignees: ""

body:
  - type: markdown
    attributes:
      value: |
        Thank you for reporting a problem in NIDAR Rescue GCS. Please provide as much detail as possible to help reproduce and resolve the issue.

  - type: textarea
    id: description
    attributes:
      label: Bug description
      description: A clear and concise description of what the bug is.
    validations:
      required: true

  - type: textarea
    id: steps
    attributes:
      label: Steps to reproduce
      description: How can we reproduce this behavior?
      placeholder: |
        1. Launch GCS console via 'run_gcs.bat'
        2. Switch to 'SURVIVORS' navigation tab
        3. Click on ...
        4. See error ...
    validations:
      required: true

  - type: textarea
    id: expected
    attributes:
      label: Expected behavior
      description: A clear description of what you expected to happen.
    validations:
      required: true

  - type: input
    id: environment
    attributes:
      label: Operating System & Python version
      description: e.g. Windows 11 / Ubuntu 22.04 LTS, Python 3.11.9, PyQt6 6.7.1
    validations:
      required: true

  - type: textarea
    id: logs
    attributes:
      label: Console output / Log trace
      description: Paste any terminal tracebacks or log output here.
