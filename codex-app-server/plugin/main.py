from dify_plugin import DifyPluginEnv, Plugin

# codex turns can take minutes; give the plugin runtime a generous timeout.
plugin = Plugin(DifyPluginEnv(MAX_REQUEST_TIMEOUT=600))

if __name__ == "__main__":
    plugin.run()
