Follow the instructions in the agent.md and the hackthon-instruction.pdf to setup the following for the agent simulations:

1. onboard the databricks omnigent for the agent orchestration and management: https://github.com/omnigent-ai/omnigent

Request: build an end-to-end working example using the omnigent framework for a multiagent research and validation system

implement the multiagent workflow using and following the best practice as suggested by databricks such that it performs the following steps strictly:

a) read the seed/source paper and extract out the suggested follow up works/directions (maximum 3), the subsequent agent loops

b) critique the suggestions, validate proposals and produce artifacts for validations

c) spin off as many agents as needed for reading literature, implementations and experimentations; make sure the produced artifacts, especially data is managed nicely for reproducability.

d) loop from the until a certain "novelty" criteria is met.

Use the paper here as the example source: https://arxiv.org/abs/2607.24975

Aceeptance:
- baseline simulations and or main results from the paper can be reproduced and validated
- at least one follow up research implemented
