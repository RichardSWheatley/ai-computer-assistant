"""The learning layer: RITA learns the system instead of assuming it.

Three pieces, one rule. The coding agent — which runs ON this machine
and may search online — investigates what RITA's own detection can't
see (`investigate`); nothing it says is trusted until RITA has
validated it deterministically herself. Validated findings persist as
machine facts (`facts`) that the detectors then use directly. Beyond
facts, the agent can build small reusable tools (`toolsets`) that RITA
smoke-validates, keeps, and reruns to automate processes; and every
chat can bind its own repo/area (`chats`).
"""
