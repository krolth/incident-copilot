from triage.approaches import fixed, multi_agent, single_agent

APPROACHES = {"fixed": fixed.run, "single": single_agent.run, "multi": multi_agent.run}
