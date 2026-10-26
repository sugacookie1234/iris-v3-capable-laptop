# Internet research

IRIS can research public information without opening a browser window. Say
**“Search the web for the latest…”**, **“Search online for…”**, or
**“Look up … online.”** Typing `/search your question` uses the same path.
The response displays **WEB SEARCH** and a list of clickable sources. Source links
open in Google Chrome from the standalone Windows app. Replies can be spoken as usual.

The existing OpenRouter key and configured model are reused. No separate search
account is required. OpenRouter's `web` plugin is explicitly enabled for these
requests, using the Exa engine with up to three requested results. Search consumes
**OpenRouter credit**, including when the selected model is free. Fish Audio credit
is separate. Current fees are described in [OpenRouter's official web search
documentation](https://openrouter.ai/docs/features/web-search); provider prices can change.

Search is triggered by a leading explicit command. Ordinary chat, local tasks,
notes searches, and council requests do not silently incur a web-search charge.
For example, “What is new in Python?” stays ordinary chat; “Search the web for what
is new in Python” performs research. Automatic decisions about when to search and
web-grounded council deliberations are possible later extensions.

Only the current research question and a short research instruction are sent in
this request. Saved memories, local documents, microphone audio and previous chat
history are not attached to the search. The answer and its source links then join
the current conversation history for follow-up discussion. The question reaches
OpenRouter and its search/model services, so use public research questions.

Web results are treated as untrusted reference material. This research call has no
local tools, shell access, account sessions or ability to perform actions. Provider
annotations supply the source links; malformed, local and unsupported-scheme links
are filtered. A response without usable sources is reported as unverified instead
of being presented as a successful web answer. Sources are not a guarantee of
accuracy: compare dates and evidence for consequential decisions.

This adds public search and source excerpts, not logged-in website automation,
downloads, purchases, email, SMS, or phone calls. Weather and market widgets keep
their existing data connections. IRIS still runs locally as a Windows app while
its configured online providers require internet access.

If search fails, the interface reports the provider error. A credit error requires
OpenRouter API balance, not a Fish Audio top-up. A non-OpenRouter chat endpoint is
supported for ordinary conversations, but this search integration needs the
OpenRouter endpoint and key selected in `setup.bat`.
