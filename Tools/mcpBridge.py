import maya.cmds as cmds

# Port the MayaMCP bridge server (Maya bridge/src/maya_mcp_server.py) connects to.
MCP_BRIDGE_PORT = ':50007'


def launch_mcp_bridge():
	"""
	Opens Maya's command port for the MayaMCP bridge, allowing the external
	MCP server to drive this Maya session. Safe to run multiple times.
	"""
	try:
		cmds.commandPort(name=MCP_BRIDGE_PORT)
	except RuntimeError:
		cmds.inViewMessage(amg='MCP bridge is already <hl>running</hl>.', pos='midCenter', fade=True)
		return

	cmds.inViewMessage(amg='MCP bridge <hl>started</hl> on port 50007.', pos='midCenter', fade=True)
