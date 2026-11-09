# Design traceability

<!-- literate-ai:authority-reviewed sha256:ded5957acf206f6759d1f598dd82b845dae018193fc2b1de160c95d5b601db53 -->

[Project guide](../README.md) → design traceability

Behavior belongs in Component specifications; target variance belongs in Flavors;
conversion technique belongs in exact skills; execution order belongs in workflows;
model eligibility belongs in routing; validation and authorization remain framework
policy. The manifest selects the source-intelligence provider, while its local database
remains
derived evidence outside source authority. Changes should update the owning artifact,
its nearby explanation or diagram,
and an end-to-end test. Illustrations aid understanding; prose requirements and
acceptance scenarios remain normative. See the [project map](../user/project-layout.md).

The retained application builds wheel/source distributions with the root Makefile.
Linux desktop entries launch the dedicated installed environment. Release policy
mirrors the package version and gates the retained suite; GitHub CI also exercises
the installed wheel. The wrapper Component has no package Flavor, so its native
`litai package` gate is inapplicable; original-source packaging remains authoritative.
