# Environment profiles and configuration rules

| Profile | Purpose | Real data | Adapters | Storage/auth |
|---|---|---|---|---|
| `test` | Deterministic automated checks | Always rejected | Fixture placeholders | Local synthetic/fake |
| `demo` | Default local application | Always rejected | Fixture placeholders | Local synthetic/fake |
| `staging` | Future firm-owned preproduction | Disabled unless separately authorized | Fixture adapters rejected | Private cloud/SSO required |
| `production` | Future authorized deployment | Disabled unless separately authorized | Fixture adapters rejected | Private cloud/SSO required |

The default is `demo` and `ALLOW_REAL_CALL_DATA=false`. Slice 0 has no route or model capable of
accepting a call.

For `staging` or `production`, startup rejects:

- authentication other than `sso`;
- missing, short, demo, example, placeholder, local, or test secrets;
- storage other than `private_cloud`, or an example/missing bucket;
- fixture call source, transcriber, or analyzer;
- any call source except `disabled` or the future `manual_upload` boundary;
- any transcriber or analyzer other than `disabled` in this slice;
- unapproved or non-positive audio, transcript, analysis, or audit retention;
- debug mode;
- empty, wildcard, non-HTTPS, or localhost CORS origins;
- local, example, placeholder, or weak database configuration;
- real-call mode without both explicit authorization and a non-placeholder approval reference.

Real-call authorization is represented in validation so it can fail closed, but this does not
grant authority and does not make real processing available. The roadmap preflight remains a
separate stop condition.

Configuration values are never dumped or included in an exception log. Only the content-free
`unsafe_configuration` code is emitted when process startup is rejected.
