---
name: readmission-analysis
description: Analyze 30-day hospital readmissions in the lakehouse. Use when
  asked about readmission rates, their drivers, or comparisons between groups.
---
# Readmission analysis

## Definitions
- Use the governed metric readmission_rate_30d from list_tables; never
  invent another definition.
- readmit_30d in v_admission_outcomes is 1 when the same patient is
  admitted again within 30 days of discharge.

## Steps
1. Call list_tables, then describe_table for every table you will query.
2. Compute the overall rate first, then the requested breakdown, reporting
   the number of admissions (n) for every group.
3. Do not report any group with fewer than 20 admissions.
4. For clinical context, use search_notes and quote at most two short
   excerpts, each with its admission ID.
5. Say that the results show associations, not causes.

## Output
A two-sentence answer, a table of groups with n and rate, and one line on
data limitations.
