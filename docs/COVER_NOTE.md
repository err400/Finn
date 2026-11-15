# Covering note draft

Subject: ENAM Founding AI Engineer Build Challenge — FINN submission

Hello ENAM team,

Please find my FINN prototype submission:

- Repository: https://github.com/err400/Finn
- Live demo: https://finn-three-brown.vercel.app
- Codex development history: **attach the actual exported ZIP separately**

FINN connects a portfolio digest, deterministic EOD/category alerts, primary-source company research, and contextual professional-network recommendations. Its central interaction is: what happened, why review it, where is the evidence, and who could add context?

I prioritized verifiable behavior over breadth: financial calculations use Decimal, retrieval preserves PDF page numbers, and the model selects exact source sentences that are validated before display. All network profiles and relationship edges are explicitly synthetic and remain outside inference prompts. The frontend and API include missing-evidence, stale-source, and provider-failure states.

The verified local dataset includes 18 companies, 1,872 EOD observations, 32 parsed primary documents across three companies, and 22 selected announcements across two companies. This is deliberately labeled partial coverage, not a complete NSE/BSE archive. Research discovery is operator-reviewed; general guidance-to-actual reconciliation, real-time monitoring, and production investor authentication remain future work.

The repository documents architecture, setup/deployment, test commands, source provenance, privacy boundaries, costs, and limitations. The demo walkthrough starts with a historical event, its filing citation and synthetic connection, then a saved alert and primary-grounded company research.

Regards,
Yuvika
