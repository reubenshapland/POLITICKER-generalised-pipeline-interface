# Declarative pipeline definitions

GET separates *what* a coding pipeline should do from *how* it is executed. A researcher describes a pipeline in a declarative definition, and the infrastructure executes it. This makes a pipeline something that can be read, reviewed, versioned and rerun by people who did not write the software. The codebooks in this repository are the simplest case: a definition with a single coding step.

## Principles

1. **One logical unit per execution.** A definition describes how one unit is processed, for example one speech or one document. Which units are processed, and when, is decided outside the definition by the run that applies it. A definition never discovers or iterates over a corpus.
2. **Steps use registered capabilities.** Each step names one capability, a reusable building block, and the strategy that implements it, with its configuration. Examples:
   - loading a document
   - splitting it into chunks
   - applying deterministic rules
   - invoking a model for structured generation or a decision
   - saving the result

   Definitions contain no executable code, database queries or file paths, so a researcher-authored definition is restricted to a vetted catalogue of capabilities.
3. **Explicit data contracts.** The definition declares the schema of the data passed between steps, and the schema of the final output. A step's inputs are bound explicitly to the unit or to earlier steps' outputs. Unknown capabilities, missing bindings and malformed schemas fail when the definition is loaded, before any model is called.
4. **Frozen, content-addressed execution.** When a run is created, the definition is resolved into an execution plan and frozen with a content hash. The plan includes the schemas, the prompts, the model configuration and the exact capability versions. Editing a definition never changes a run already under way, and every output can be traced to the frozen plan that produced it.

## Illustrative example

The example below shows the shape of a definition. It is illustrative and simplified, not a production definition. It classifies one document by checking deterministic rules first, and asks a decision model only when no rule applies.

```yaml
id: example-session-classify
version: 1
unit: one transcript document

schemas:
  session_type:
    type: object
    properties:
      session_type: { type: string, enum: [QUESTIONS, STATEMENT, DEBATE, PROCEDURAL] }
      confidence:   { type: number }
    required: [session_type, confidence]

prompts:
  classify: >-
    Classify the proceedings by their format: questions and answers, a
    statement followed by questions, a debate on a motion or bill, or procedure.

steps:
  - id: load
    capability: source
    strategy: document
    inputs: { document_id: $unit.document_id }

  - id: rules
    capability: transform
    strategy: title_rules          # e.g. a title containing "Prime Minister" -> QUESTIONS
    inputs: { title: $steps.load.output.title }

  - id: classify
    capability: llm_invocation
    strategy: decision             # decision model: typed answer plus probabilities
    when: $steps.rules.output.matched == false
    config:
      model: typesafe/jev-1.14     # pinned version
      instructions: classify
      output_schema: session_type
      criteria:
        QUESTIONS: Members question a minister, who answers.
        STATEMENT: A minister makes a statement, followed by questions.
        DEBATE: A debate on a motion or a bill.
        PROCEDURAL: Procedural business.
    inputs: { state: { title: $steps.load.output.title, text: $steps.load.output.text } }

  - id: save
    capability: persistence
    strategy: output_store
    inputs: { record: $steps.classify.output }
```

## A working miniature

`pipelines/ai-discourse-uk-us.yaml` is a working miniature of this design, run by `src/getref/pipeline.py`. It has four steps: two speech segmenters, one for UK Hansard debates and one for the US Congressional Record; an AI-term filter; and a coding step that refers to a codebook. The filter keeps every speech in a section whose title contains an AI term, and elsewhere only speeches that mention one. The definition is validated when it is loaded, then frozen together with its codebook into a plan identified by a content hash, and outputs are written under that hash. It omits the full runtime's orchestration, storage and capability catalogue.

## Status

An internal runtime for these definitions is in development in the authors' production system. A first classification pipeline already runs on parliamentary transcripts, using a decision model behind deterministic rules. The runtime itself is not part of this repository. Researcher-authored definitions, stored as validated and immutable versions, are planned for the hosted interface. See [scope and roadmap](scope-and-roadmap.md).
