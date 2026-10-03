# Track 4 Development submission

The tracked template is an input to the official packer. It deliberately omits `team_id` and
`descriptor_digest`: `qfbench2 submission pack` derives both, validates the completed descriptor,
and writes them into the ZIP. Do not add a placeholder `team_id`; the packer refuses a value that
does not match the Team Number and Team Key.

Current participant image:

```text
ghcr.io/yif-design/agenthon2026-t4@sha256:f0d58b7b69906449034a09273ad545d6df3d42286ac4dffbde7ca6815948408f
```

Verified properties:

- anonymously readable from GHCR;
- Linux/amd64;
- image label `qfbench2.interface_version=2.0`;
- `analyze` command smoke-tested by GitHub Actions run `37091935219`;
- anonymous registry manifest request returned HTTP 200 for the same immutable digest;
- final no-model audit passed all 11 public units and all 78 entities with zero local validation
  errors in 19.1 seconds; the combined answer size was 99,885 bytes;
- all 8 OCI layers and 5,893 tar entries were streamed and checked for the macOS
  `com.apple.provenance` attribute reported in official Track 4 issue #16; none contained it;
- descriptor declares the official House Nemotron snapshot and Apache-2.0 license.

Install the official toolkit in a temporary directory or other clean Python 3.13 environment,
then pack from `t4-agent`:

```bash
qfbench2 submission pack \
  --descriptor submission.dev.template.json \
  --team-number 297 \
  --out submissions/submission.zip
```

Enter the Team Key only at the hidden prompt. Do not put it on the command line. The resulting ZIP
must contain exactly `submission.json` and `team-claim.json`. Upload that ZIP to the Track 4
Development page under **My Submissions**. Do not upload the template directly and do not replace
the image digest with the floating `:dev` tag.

After any new image build, update the digest in both this file and the template, then repack. The
Team Key is not included in the ZIP, but the ZIP contains the team proof and should remain private.
