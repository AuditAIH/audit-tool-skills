# Privacy Policy

This plugin forwards the conversation payload (`query`, `conversation_id`,
`app_id`, `user_id`) to the codex-app-server HTTP service that you configure
in the provider credentials (`server_url`). No data is sent to any third
party other than the configured codex-app-server endpoint.

The plugin itself does not store any conversation data. Conversation state
(the `conversation_id` -> codex thread mapping and the codex rollout) is
persisted by the codex-app-server service and the codex `app-server` process
that you operate.
