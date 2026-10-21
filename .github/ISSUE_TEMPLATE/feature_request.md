name: Feature request
about: Suggest an improvement or new capability
title: ""
labels: ["enhancement"]
assignees: ""

body:
  - type: markdown
    attributes:
      value: |
        Thanks for the suggestion. Please describe the feature and why it matters.

  - type: textarea
    id: idea
    attributes:
      label: Feature summary
      description: What feature would you like to add?
    validations:
      required: true

  - type: textarea
    id: problem
    attributes:
      label: Why this is needed
      description: What problem does this solve?
    validations:
      required: true

  - type: textarea
    id: alternatives
    attributes:
      label: Alternatives considered
      description: Have you considered another approach?

  - type: textarea
    id: details
    attributes:
      label: Additional context
      description: Screenshots, references, mockups, or links.
