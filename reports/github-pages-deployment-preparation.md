# GitHub Pages deployment preparation

Date: 24 October 2026
Repository: `dannevdso/ahmedabad-urban-scanner`
Target domain: `ahd.da-za.com`
Status: prepared and verified locally; not committed, pushed, deployed, or connected to DNS.

## Changes

- Added `.github/workflows/deploy-pages.yml` to test, build, audit, upload only `web/dist`, deploy through GitHub Pages, and run post-deployment HTTP Range checks.
- Configured Vite through `PAGES_BASE_PATH`, defaulting to `/` for the custom domain. `npm run build:repo-url` builds for `/ahmedabad-urban-scanner/` without changing source.
- Made the logo and lazy print-boundary request base-path aware. No analytical code, GIS calculations, styles, print layouts, or report semantics changed.
- Added `web/public/CNAME` containing `ahd.da-za.com` and `.nojekyll`.
- Added `web/pages-publication-assets.json`, an explicit allowlist for the runtime publication. The detailed building-height tile inventory is derived from its existing canonical manifest.
- Added `scripts/audit_pages_publication.py`. It rejects missing or unallowlisted assets, temporary/private path classes, credential signatures, files over 100 MiB, and sites over 1 GiB; verifies PMTiles/FlatGeobuf/GeoTIFF source-to-build SHA-256 parity; and writes `web/dist/publication-manifest.json`.
- Added `scripts/check_static_range_support.py` for PMTiles, FlatGeobuf, and GeoTIFF HTTP `Range` checks.
- Expanded `.gitignore` for raw `data/`, archives, rollback/prototype outputs, local environments, build/test outputs, temporary files, and common credentials. `web/public/data/**` is explicitly re-included because it is the approved runtime derivative publication.

## Verified publication

| Check | Result |
|---|---:|
| Published files | 2,392, including the publication manifest |
| Published size | 531,651,024 bytes (507.02 MiB) |
| GitHub Pages 1 GiB limit | Pass; 542,090,800 bytes headroom |
| Largest file | `data/buildings.pmtiles`, 53,159,322 bytes |
| Files over GitHub's 100 MiB hard limit | 0 |
| Non-ignored repository candidate size | 530,955,416 bytes (506.36 MiB) |
| Binary parity | Pass for 1 PMTiles, 8 FlatGeobuf, and 3 GeoTIFF files |
| Detailed building-height tiles | 2,328 present with declared byte sizes |
| Local-profile manifest assets | 11 hash/size contracts verified |
| CNAME | `ahd.da-za.com` |

The publication manifest lists every deployed file except itself, because a file cannot contain its own final SHA-256. It records path, byte size, content type, and SHA-256 for the other 2,391 files.

## Tests and builds

- Frontend: **23 test files passed, 1 skipped; 217 tests passed, 4 skipped**.
- Python: **143 tests passed**.
- Custom-domain root build: passed and passed the publication audit.
- Repository-URL build at `/ahmedabad-urban-scanner/`: passed, passed the publication audit, and produced repository-prefixed asset/logo URLs.
- Local production preview: loaded the map UI with no browser console errors.
- Vite reported one non-fatal bundle-size warning for the 1.466 MB main JavaScript chunk. It does not violate GitHub's file limit and was not changed to avoid altering the frontend architecture.

## HTTP Range status

The live check is intentionally unresolved until the first GitHub Pages deployment. Local Vite preview returned `200` rather than `206` for test ranges against:

- `data/buildings.pmtiles`
- `data/local-profile/centrality.fgb`
- `data/local-profile/ndvi.tif`

This local result must not be treated as evidence about GitHub Pages. The deployment workflow runs the same check against the deployed Pages URL and fails the `verify-live-ranges` job unless all three responses are `206 Partial Content` with valid `Content-Range` and exact byte counts. Do not consider PMTiles, FlatGeobuf, or GeoTIFF production access verified until that job passes.

## Exact deployment steps — not performed

1. Review the currently staged source, workflow, and approved `web/public` runtime assets before committing.
2. Commit and push to `dannevdso/ahmedabad-urban-scanner`; merge to `main` only when ready to deploy.
3. In GitHub **Settings → Pages**, select **GitHub Actions** as the source.
4. Optional no-deploy repository-path test: run **Deploy Ahmedabad Urban Scanner to GitHub Pages** manually with `base_path=/ahmedabad-urban-scanner/` and `deploy=false`.
5. For the custom-domain deployment, leave `PAGES_BASE_PATH` unset or set the repository Actions variable to `/`.
6. Push to `main`, or manually run the workflow with `base_path=/` and `deploy=true`.
7. Require the build, publication audit, deployment, and `verify-live-ranges` jobs to pass.
8. Only after deployment verification, configure `ahd.da-za.com` in GitHub Pages settings and then change WordPress/DNS. Verify GitHub's DNS check and HTTPS before enabling the public domain.

## Unresolved issues

- GitHub Pages' real HTTP Range behavior for these files is unverified until deployment.
- `origin` is configured for `dannevdso/ahmedabad-urban-scanner`, and the approved files are staged on `github-pages-prep`; no commit, push, deployment, Pages activation, or DNS change has been performed.
- The site is 507.02 MiB, within the 1 GiB limit but large enough that future asset additions must continue to pass the audit and should account for GitHub Pages' bandwidth limit.

## Limit references

- GitHub Pages limits: https://docs.github.com/en/pages/getting-started-with-github-pages/github-pages-limits
- GitHub repository file-size limits: https://docs.github.com/en/repositories/working-with-files/managing-large-files/about-large-files-on-github
- Vite static deployment guidance: https://vite.dev/guide/static-deploy.html
