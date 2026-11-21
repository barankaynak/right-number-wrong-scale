# Release note

This archive was built from commit `26faf52` of the development repository's `main` branch. The files below were changed for the public release: a private host address, a service endpoint and local paths were replaced, and the two coder sheets of the mutation-quality audit, whose file names carried the coders' first names, were renamed `B4_coding_coder1.csv` and `B4_coding_coder2.csv` (with every reference to them). Nothing else differs from the commit. `original` is the SHA-256 of the file at that commit, `released` that of the file here.

| file | original | released |
|---|---|---|
| `laadt-dss/backend/app/core/config.py` | `bf239971fd931225f981c4ba6363f639876f3755399e4fc3e7ef353ea1e35f83` | `9c288c71000f5580fd81b7a90aec7a125de9ccb66631ecc58aa55146c58ed04d` |
| `laadt-dss/backend/experiments/gfp_benchmark/PREREGISTRATION.md` | `a0c5fc386bec6c9c989f052db898844b2fb41e79613be328145e945cf9577f17` | `d2a54fbb0227b44f6d97bcbceea83366bc4a6279060666b6af94491f206fb42e` |
| `laadt-dss/backend/experiments/gfp_benchmark/b4_mutation_quality/B4_results.json` | `4f94c5b24aa83eb5085c32819c54f734ed136d9c4e6b4b3fa666d700ca249d64` | `44014cd15778d08538bdf09e4691e7616d507d9ac11c08703bbf8b49b98004cc` |
| `laadt-dss/backend/experiments/gfp_benchmark/b4_mutation_quality/compute_b4_kappa.py` | `c3fc7beda71b617f5529fd3a24b9fe55047c8fff47db6225f061b548be2b371b` | `6960e6b4024d3325539dcf5a9141e73e3f35c0053954782a46eb03345792c8f8` |
| `laadt-dss/backend/experiments/gfp_benchmark/b4_mutation_quality/make_b4_adjudication_tool.py` | `b083a635738a728903bb3b142a443e4ec2d7989b54001d04c442cb549920661a` | `a6eed29331a37f76782f3c4cd3939bbb0356603c3436eeacc7b9e9f691c186f0` |
| `laadt-dss/backend/experiments/gfp_benchmark/manuscript_audit/report.json` | `bbfdfa771a804279f1ef91e840af0740d9ff11579128f594bec7fbc30571703c` | `53242aed666af1e0bd63f12493bb70bbe178223de183f7620a2b63c7e512e9b1` |
| `laadt-dss/backend/experiments/gfp_benchmark/manuscript_audit/report.md` | `f7a30d191d89ea5dad4ea22f602ae31a3e7886b26de862d6665bc892faa8e58f` | `1e396434adf82236c437cb5f390538a631d706d3bee69ac49cf8c343f02d9422` |
| `laadt-dss/backend/experiments/gfp_benchmark/run_a30_evren.py` | `9135c6c56770f9178fe0d1c1cbc86aebc359913be20fb294efdeb54228c35d03` | `8fe940ed727c76244ac101d26c792ca50e69103fd196f2f3c88515498f7fb136` |
| `laadt-dss/docker-compose.yml` | `8add23a14ae4cc5a1d5eb0dc8653986eab6039a64f71fd31bdd6617e1d70310f` | `e437d0964f793b8f406c95eb6f2531f6e19ac29449209a3c49e42374f995b934` |

Left out: run logs (`*.log`) and Seafile conflict copies. The blinding keys of the two coding audits (`A8_guard_key.csv`, `B4_guard_key.csv`) are included; blinding ended when coding was complete.
