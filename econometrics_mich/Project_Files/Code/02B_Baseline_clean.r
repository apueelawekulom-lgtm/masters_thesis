# ============================================================
# US–China Trade War Project
# Script: 02B_baseline_clean.R
#
# FINAL baseline (decided in 02A):
#   Estimator : PPML (fepois) baseline; OLS (feols) companion
#   Panel     : top-100 destinations + aggregated RoW  (df100)
#   FE        : saturated -> hs6^importer_grp + importer_grp^year + hs2^year
#   Cluster   : hs6 (treatment is assigned at the product level)
#   Control   : NONE. preus_bin:year is redundant under this FE (degenerate SEs,
#               no effect on the tariff coefficient); FEs absorb the confound.
#
# Contents:
#   1. Data: build df100 (top-100 + RoW) with pre_us_share
#   2. Baseline pooled table (PPML + OLS)
#   3. Baseline event studies (PPML + OLS)
#   4. Heterogeneity: pre-US-share as TREATMENT (pooled)
#   5. Heterogeneity event studies (full + drop-COVID; COVID caveat)
# ============================================================

rm(list = ls()); gc()

# ------------------------------------------------------------
# 0. Packages + settings
# ------------------------------------------------------------
lapply(c("dplyr", "fixest", "tidyr"), library, character.only = TRUE)

setFixest_nthreads(0)        # all cores
PPML_TOL <- 1e-6             # tight tolerance for final reported specs

root        <- "/Users/michelleshi/Documents/BSE/Term 3/Thesis/Project_Files"
output_path <- file.path(root, "Output")

# Saturated FE used throughout (RoW panel)
FE <- ~ hs6^importer_grp + importer_grp^year + hs2^year

# Thin PPML / OLS wrappers: fix the FE, cluster, tolerance once
ppml <- function(lhs_rhs, data = df100)
  fepois(lhs_rhs, data = data, cluster = ~ hs6, fixef.tol = PPML_TOL)
ols  <- function(lhs_rhs, data = df100)
  feols(lhs_rhs, data = data, cluster = ~ hs6)

# ------------------------------------------------------------
# 1. Data: top-100 + RoW panel with pre-US-exposure share
# ------------------------------------------------------------

# pre-US-exposure share (2015-2017), built on the FULL panel incl. US
pre_us_share <- readRDS(file.path(output_path, "df_hs12.rds")) %>%
  filter(year >= 2015, year <= 2017) %>%
  group_by(hs6) %>%
  summarise(
    us_exports_pre    = sum(exports[importer == 842], na.rm = TRUE),
    world_exports_pre = sum(exports, na.rm = TRUE),
    .groups = "drop"
  ) %>%
  mutate(pre_us_share = us_exports_pre / world_exports_pre) %>%
  select(hs6, pre_us_share)

# main panel: drop US destination, attach exposure
df <- readRDS(file.path(output_path, "df_hs12.rds")) %>%
  filter(importer != 842) %>%
  left_join(pre_us_share, by = "hs6") %>%
  mutate(
    pre_us_share = replace_na(pre_us_share, 0),
    preus_bin = factor(            # kept only for the treatment-role interaction
      case_when(
        pre_us_share == 0    ~ "0",
        pre_us_share <= 0.10 ~ "Low US exposure",
        pre_us_share > 0.10  ~ "High US exposure"
      ),
      levels = c("0", "Low US exposure", "High US exposure")
    )
  )

# rank destinations on pre-shock years (2015-2017); keep top 100, rest -> ROW
imp_rank <- df %>%
  filter(year >= 2015, year <= 2017) %>%
  group_by(importer) %>%
  summarise(v = sum(exports), .groups = "drop") %>%
  mutate(share = v / sum(v)) %>%
  arrange(desc(share))

keep100 <- imp_rank %>% slice_max(share, n = 100) %>% pull(importer)
cat("top-100 cumulative share:",
    round(sum(imp_rank$share[imp_rank$importer %in% keep100]), 3), "\n")  # 0.978

# aggregate to top-100 + RoW
df100 <- df %>%
  mutate(importer_grp = ifelse(importer %in% keep100, as.character(importer), "ROW")) %>%
  group_by(hs6, hs2, importer_grp, year, post2018, tariff_rate,
           preus_bin, pre_us_share) %>%
  summarise(exports = sum(exports, na.rm = TRUE), .groups = "drop") %>%
  mutate(log_exports = log(exports + 1))   # +1 matches the build's log definition

stopifnot(min(df100$exports, na.rm = TRUE) > 0)   # no zero cells after aggregation
rm(pre_us_share, df, imp_rank); gc()              # keep df100 only

# ============================================================
# 2. BASELINE — pooled (PPML + OLS)
# ============================================================
# PPML 0.542 (SE .333, p~.10); OLS 0.728*** (SE .127). Same sign, OLS precise,
# PPML marginal. Pooled is a summary; the EVIDENCE is the event study below.

m_ppml <- ppml(exports     ~ tariff_rate:post2018 | hs6^importer_grp + importer_grp^year + hs2^year)
m_ols  <- ols (log_exports ~ tariff_rate:post2018 | hs6^importer_grp + importer_grp^year + hs2^year)

tab_baseline <- etable(
  "PPML (baseline)" = m_ppml,
  "OLS (companion)" = m_ols,
  digits = 3, se.below = TRUE, fitstat = ~ n + r2
)
print(tab_baseline)

# ============================================================
# 3. BASELINE — event studies (PPML + OLS)
# ============================================================
# PPML: flat pre-trend (2012-16 ~0), SIGNIFICANT 2018 (0.33, p=.02), marginal
# 2019/2023/2024, 2022 large but imprecise, 2020 COVID dip. OLS: precise post,
# but significant negative pre-trend 2012-14 -> PPML is the headline figure.

m_es_ppml <- ppml(exports     ~ i(year, tariff_rate, ref = 2017) | hs6^importer_grp + importer_grp^year + hs2^year)
m_es_ols  <- ols (log_exports ~ i(year, tariff_rate, ref = 2017) | hs6^importer_grp + importer_grp^year + hs2^year)

tab_es_baseline <- etable(
  "PPML event study" = m_es_ppml,
  "OLS event study"  = m_es_ols,
  digits = 3, se.below = TRUE, fitstat = ~ n
)
print(tab_es_baseline)

# Figure: PPML and OLS side by side, shared axis
par(mfrow = c(1, 2))
iplot(m_es_ppml, ref.line = TRUE, main = "PPML (top-100 + RoW)",
      xlab = "Year", ylab = "Coef. on tariff x year (rel. 2017)", ylim = c(-1, 2))
abline(h = 0, lty = 2, col = "grey50")
iplot(m_es_ols,  ref.line = TRUE, main = "OLS (top-100 + RoW)",
      xlab = "Year", ylab = "Coef. on tariff x year (rel. 2017)", ylim = c(-1, 2))
abline(h = 0, lty = 2, col = "grey50")
par(mfrow = c(1, 1))

# ============================================================
# 4. HETEROGENEITY — pre-US-share as TREATMENT (pooled)
# ============================================================
# Triple interaction: does the diversion concentrate in formerly-US-dependent
# goods? Pooled interaction is large+positive (OLS sig, PPML wide). BUT see the
# event study in section 5 -- the interaction is driven by a 2020 COVID spike and
# does NOT survive dropping the pandemic years. Report as SUGGESTIVE, not causal.

m_ppml_trt <- ppml(
  exports ~ tariff_rate:post2018 + tariff_rate:post2018:pre_us_share |
    hs6^importer_grp + importer_grp^year + hs2^year
)
m_ols_trt  <- ols(
  log_exports ~ tariff_rate:post2018 + tariff_rate:post2018:pre_us_share |
    hs6^importer_grp + importer_grp^year + hs2^year
)

tab_het <- etable(
  "PPML (US treatment)" = m_ppml_trt,
  "OLS (US treatment)"  = m_ols_trt,
  digits = 3, se.below = TRUE, fitstat = ~ n
)
print(tab_het)

# ============================================================
# 5. HETEROGENEITY — event studies (full + drop-COVID)
# ============================================================
# Two paths per model: i.select = 1 -> tariff x year; i.select = 2 -> pre-US-share
# x year (the heterogeneity term). Full sample vs dropping 2020-21.

m_es_het <- ppml(
  exports ~ i(year, tariff_rate, ref = 2017) + i(year, pre_us_share, ref = 2017) |
    hs6^importer_grp + importer_grp^year + hs2^year
)
m_es_het_nocovid <- ppml(
  exports ~ i(year, tariff_rate, ref = 2017) + i(year, pre_us_share, ref = 2017) |
    hs6^importer_grp + importer_grp^year + hs2^year,
  data = filter(df100, !year %in% c(2020, 2021))
)

# Full sample: tariff path (clean) vs pre-US-share path (2020 spike then decays)
par(mfrow = c(1, 2))
iplot(m_es_het, i.select = 1, ref.line = TRUE, main = "Tariff x year",
      ylab = "Coef. (rel. 2017)", ylim = c(-1, 2)); abline(h = 0, lty = 2, col = "grey50")
iplot(m_es_het, i.select = 2, ref.line = TRUE, main = "Pre-US-share x year",
      ylab = "Coef. (rel. 2017)"); abline(h = 0, lty = 2, col = "grey50")
par(mfrow = c(1, 1))

# ------------------------------------------------------------
# Objects retained:
#   tables : tab_baseline, tab_es_baseline, tab_het
#   models : m_ppml, m_ols, m_es_ppml, m_es_ols,
#            m_ppml_trt, m_ols_trt, m_es_het, m_es_het_nocovid
#   data   : df100
# ------------------------------------------------------------