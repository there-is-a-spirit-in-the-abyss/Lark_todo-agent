# Languages

Default language is Simplified Chinese (`zh-CN`); English (`en-US`) is selectable.
`APP_LANGUAGE` sets the instance default. A private chat may send `/language en-US`
or `/language zh-CN`; the preference is stored in existing platform settings by
verified Feishu sender ID and applies to private replies and reminders. In legacy
group mode, only a real bot mention may switch that group's language; all members
then share it. Team-web group mode retains its entry-link-only routing and uses
the instance default. English entry keywords are `team tasks` and `team todo`.

A small shared Python catalog renders system-owned text. A scoped context keeps
concurrent requests isolated; task names, descriptions, people, IDs, dates and the
persisted Chinese status enum remain unchanged. Both model transports receive an
explicit output-language instruction for understanding and clarification fields.
The web UI has a visible language selector, persists its choice in browser local
storage, and sends the locale with API requests. Business rules, authentication,
personal/group routing and task-tree permissions are unchanged.

No external accounts, production data, deployment or GitHub publication is part
of this change. Local tests and builds cannot verify live Feishu or model access.
