# ============================================================
# US–China Trade War Project
# Script: 02A_regressions_testing.R  (descriptive analysis)
#
# Estimator: PPML (fepois) is the baseline (level-weighted; what
# our advisors prefer; the natural object for "how much trade was
# reallocated"). OLS shown as the proportional-margin companion.
#
# Tier 1 : core (main table + centrepiece event study)
# Tier 2 : robustness (FE ladder, clustering, bins, sample windows)
# Tier 3 : characterisation (corridor-size + pre-US-share heterogeneity)
# NEW : AGGREGATION OF ROW FOR NON TOP 100 IMPORTERS
# ============================================================

rm(list = ls()); gc()

# ------------------------------------------------------------
# 0. Packages
# ------------------------------------------------------------
lapply(c("dplyr", "fixest", "ggplot2", "tidyr"), library, character.only = TRUE)

# fixest speed settings reused throughout
setFixest_nthreads(0)          # all cores
PPML_TOL <- 1e-4               # looser FE tolerance for fepois speed

# ------------------------------------------------------------
# 1. Paths + data
# ------------------------------------------------------------
root        <- "/Users/michelleshi/Documents/BSE/Term 3/Thesis/Project_Files"
output_path <- file.path(root, "Output")

# Full panel (incl. US). Needed ONLY to build pre-US-exposure share, then dropped
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

# Main analysis panel (US destination removed) + merge controls/bins
df <- readRDS(file.path(output_path, "df_hs12.rds")) %>%
  filter(importer != 842) %>%
  left_join(pre_us_share, by = "hs6") %>%
  mutate(pre_us_share = replace_na(pre_us_share, 0)) %>%
  mutate(
    preus_bin = case_when(   # US-exposure bins (CONTROL role)
      pre_us_share == 0                 ~ "0",
      pre_us_share <= 0.10              ~ "Low US exposure",
      pre_us_share > 0.10               ~ "High US exposure"
    ),
    preus_bin = factor(
      preus_bin,
      levels = c(
        "0",
        "Low US exposure",
        "High US exposure"
      )
    )
  )

# LINEARITY CHECK: Tariff-increase groups (functional-form / dose-response check).
# Untaxed products are the comparison group; taxed products are split into
# three equal-sized groups (low / mid / high increase). If a bigger tariff
# means a bigger trade effect, the three groups should line up in order.
pos_cuts <- quantile(df$tariff_rate[df$tariff_rate > 0],
                     probs = c(0, 1/3, 2/3, 1), na.rm = TRUE)
df <- df %>%
  mutate(
    tariff_grp = factor(
      case_when(
        tariff_rate == 0                                   ~ "0 (ref)",
        tariff_rate <= pos_cuts[2]                         ~ "Low",
        tariff_rate <= pos_cuts[3]                         ~ "Mid",
        TRUE                                               ~ "High"
      ),
      levels = c("0 (ref)", "Low", "Mid", "High")
    )
  )

rm(pre_us_share); gc()

# ------------------------------------------------------------
# Diagnostics (run once; not reported)
# ------------------------------------------------------------
mean(df$exports == 0)                       # confirm no zeros
count(df, preus_bin)                         # confirm "0" bin is a real group
count(df, tariff_grp)                        # tercile group sizes
print(pos_cuts)                              # where the positive-rate terciles cut
mean(df$imputed_zero)                        # share of obs with imputed-zero tariff

# preus_bin "0" composition: how many hs6 are genuinely zero-US vs simply
# absent from the 2015-17 pre-period (the latter also get pre_us_share = 0).
df %>%
  filter(pre_us_share == 0) %>%
  distinct(hs6) %>%
  nrow()                                     # distinct hs6 in the "0" exposure bin

df %>% # treatment vs control overlap: is tariff variation concentrated in one bin?
  distinct(hs6, .keep_all = TRUE) %>%
  with(table(preus_bin,
             cut(tariff_rate,
                 breaks = quantile(tariff_rate, c(0,.25,.5,.75,1), na.rm = TRUE),
                 include.lowest = TRUE))) #good treatment variation!

# NOTE on grouping + linearity decision:
# percentiles of positive tariff_rate sit at ~10.0% and ~11.5%, so "Mid" is a
# ~1.5pp-wide spike holding the most obs while groups are very uneven
# (Low 2.07M / Mid 3.02M / High 1.13M). These are therefore NOT clean terciles.
# BUT THIS is the core justification for the CONTINUOUS baseline: the change-in-
# tariff measure is spiked near the list rates, so any binning is arbitrary and
# unstable (membership flips with small cutpoint changes). 
# ============================================================
# TIER 1：CORE (main table + centrepiece event study)
# ============================================================

## 1a. Pooled, continuous, US-exposure control (:year) ---------
m_ppml <- fepois(
  exports ~ tariff_rate:post2018 + preus_bin:year |
    hs6^importer + importer^year + hs2^year,
  data = df, cluster = ~ hs6 + importer, fixef.tol = PPML_TOL
)
m_ols <- feols(
  log_exports ~ tariff_rate:post2018 + preus_bin:year |
    hs6^importer + importer^year + hs2^year,
  data = df, cluster = ~ hs6 + importer
)

## And add bare specs (NO US-exposure term, neither control nor treatment) -----
m_ppml_bare <- fepois(
  exports ~ tariff_rate:post2018 |
    hs6^importer + importer^year + hs2^year,
  data = df, cluster = ~ hs6 + importer, fixef.tol = PPML_TOL
)
m_ols_bare <- feols(
  log_exports ~ tariff_rate:post2018 |
    hs6^importer + importer^year + hs2^year,
  data = df, cluster = ~ hs6 + importer
)

## Side-by-side: controlled (baseline) vs bare, PPML and OLS
tab_bare_vs_ctrl <- etable(
  "PPML control" = m_ppml,        # baseline, preus_bin:year
  "PPML bare"    = m_ppml_bare,   # no US term
  "OLS control"  = m_ols,         # baseline, preus_bin:year
  "OLS bare"     = m_ols_bare,    # no US term
  drop = "preus_bin", digits = 3, se.below = TRUE, fitstat = ~ n + r2
)
print(tab_bare_vs_ctrl)



## 1b. Event study, continuous, US control --------------------
m_es_ppml <- fepois(
  exports ~ i(year, tariff_rate, ref = 2017) + preus_bin:year |
    hs6^importer + importer^year + hs2^year,
  data = df, cluster = ~ hs6 + importer, fixef.tol = PPML_TOL
)
m_es_ols <- feols(
  log_exports ~ i(year, tariff_rate, ref = 2017) + preus_bin:year |
    hs6^importer + importer^year + hs2^year,
  data = df, cluster = ~ hs6 + importer
)

# key figure: PPML and OLS side by side, shared axis
par(mfrow = c(1, 2))
iplot(m_es_ppml, ref.line = TRUE, main = "PPML",
      xlab = "Year", ylab = "Coef. on tariff x year (rel. 2017)", ylim = c(-1, 2))
abline(h = 0, lty = 2, col = "grey50")
iplot(m_es_ols,  ref.line = TRUE, main = "OLS",
      xlab = "Year", ylab = "Coef. on tariff x year (rel. 2017)", ylim = c(-1, 2))
abline(h = 0, lty = 2, col = "grey50")
par(mfrow = c(1, 1))


## add the bares on too 
m_es_ppml_bare <- fepois(
  exports ~ i(year, tariff_rate, ref = 2017) |
    hs6^importer + importer^year + hs2^year,
  data = df, cluster = ~ hs6 + importer, fixef.tol = PPML_TOL
)

m_es_ols_bare <- feols(
  log_exports ~ i(year, tariff_rate, ref = 2017) |
    hs6^importer + importer^year + hs2^year,
  data = df, cluster = ~ hs6 + importer
)

tab_es_bare_vs_ctrl <- etable(
  "PPML control" = m_es_ppml, "PPML bare" = m_es_ppml_bare,
  "OLS control"  = m_es_ols,  "OLS bare"  = m_es_ols_bare,
  drop = "preus_bin", digits = 3, se.below = TRUE, fitstat = ~ n
)
print(tab_es_bare_vs_ctrl)

# keep m_es_ppml / m_es_ols and tables; drop nothing yet (event study reused below)

# ============================================================
# TIER 2 — ROBUSTNESS
# ============================================================

## 2a. FE saturation ladder (PPML) ----------------------------
m_rung_main  <- m_ppml  # baseline already has hs6^imp + imp^yr + hs2^yr
m_rung_mid   <- fepois(
  exports ~ tariff_rate:post2018 + preus_bin:year |
    hs6^importer + importer^year,
  data = df, cluster = ~ hs6 + importer, fixef.tol = PPML_TOL
)
m_rung_lean  <- fepois(
  exports ~ tariff_rate:post2018 + preus_bin:year |
    hs6^importer + year,
  data = df, cluster = ~ hs6 + importer, fixef.tol = PPML_TOL
)

tab_ladder <- etable(
  "Saturated (hs2^yr)" = m_rung_main,
  "Mid (imp^yr)"       = m_rung_mid,
  "Lean (year)"        = m_rung_lean,
  drop = "preus_bin", digits = 3, se.below = TRUE, fitstat = ~ n
)
print(tab_ladder)
rm(m_rung_mid, m_rung_lean); gc()   
# keep baseline only; significance shrinks as you add FE as expected. 
# coefficients are fairly stable though

## 2b. Clustering robustness (re-cluster the baseline) --------
tab_cluster <- etable(
  "2-way hs6 & imp" = summary(m_ppml, cluster = ~ hs6 + importer),
  "hs6 only"        = summary(m_ppml, cluster = ~ hs6),
  "hs2 only"        = summary(m_ppml, cluster = ~ hs2),
  drop = "preus_bin", digits = 3, se.below = TRUE, fitstat = ~ n
)
print(tab_cluster) #good stability of clusters; no change

## 2c. Linearity (continuous vs tariff bins check) (PPML) -----
m_terc <- fepois(
  exports ~ i(tariff_grp, post2018, ref = "0 (ref)") + preus_bin:year |
    hs6^importer + importer^year + hs2^year,
  data = df, cluster = ~ hs6 + importer, fixef.tol = PPML_TOL
)
tab_terc <- etable(m_terc, drop = "preus_bin", digits = 3, se.below = TRUE)
print(tab_terc)
rm(m_terc); gc()

# Linearity check (PPML): Low 0.030, Mid 0.022, High 0.176* -- effect shows up
# only in the high-tariff group, so small tariff rises did little and the big
# (25%-type) rises drove the reallocation; supports using the continuous measure.

## 2d. Sample windows -----------------------------------------
# (i) drop COVID years
m_nocovid <- fepois(
  exports ~ tariff_rate:post2018 + preus_bin:year |
    hs6^importer + importer^year + hs2^year,
  data = filter(df, !year %in% c(2020, 2021)),
  cluster = ~ hs6 + importer, fixef.tol = PPML_TOL
)
# (ii) base year 2016 instead of 2017 (anticipation check) -- event study
m_es_base2016 <- fepois(
  exports ~ i(year, tariff_rate, ref = 2016) + preus_bin:year |
    hs6^importer + importer^year + hs2^year,
  data = df, cluster = ~ hs6 + importer, fixef.tol = PPML_TOL
)
tab_window <- etable("Drop COVID" = m_nocovid, drop = "preus_bin",
                     digits = 3, se.below = TRUE, fitstat = ~ n)
print(tab_window)

iplot(m_es_base2016, ref.line = TRUE, main = "PPML event study, base = 2016",
      xlab = "Year", ylab = "Coef. (rel. 2016)", ylim = c(-1, 2))
abline(h = 0, lty = 2, col = "grey50")
rm(m_nocovid, m_es_base2016); gc()

## COVID: coef rises to 0.743 (from 0.580 baseline), same sign,
# still wide SE. Effect is not a COVID artifact -- if anything COVID masked it
# (2020 dip in the event study); re-routing paused in 2020 then resumed (think: face masks).

## 2e. Drop imputed-zero tariffs (genuine zeros remain as control) -----
# Unmatched codes were imputed tariff_rate = 0 in the build (~2.7% of obs).
# Genuine matched zeros stay as the control group; here we drop ONLY the
# imputed ones to confirm the baseline is not driven by them.
m_noimpute <- fepois(
  exports ~ tariff_rate:post2018 + preus_bin:year |
    hs6^importer + importer^year + hs2^year,
  data = filter(df, !imputed_zero),
  cluster = ~ hs6 + importer, fixef.tol = PPML_TOL
)
tab_noimpute <- etable(
  "Drop imputed zeros" = m_noimpute,
  drop = "preus_bin", digits = 3, se.below = TRUE, fitstat = ~ n
)
print(tab_noimpute)
rm(m_noimpute); gc()

## imputed zeros: ynmatched codes set to 0 in the build are NOT driving the result,
# dropping them entirely leaves the effect positive/similar. Imputation is fine.

rm(m_rung_main, pos_cuts, m_ppml_bare, m_ols_bare)
gc()
# ============================================================
# TIER 3 — CORRIDOR SIZE + PRE-US EXPOSURE AS TREATMENT
# ============================================================

## 3a. Corridor-size heterogeneity ----------------------------
# baseline (pre-2017) corridor size -> terciles, then event study within each.
# Documents directly the "reallocation concentrated in small corridors" pattern.
corridor_size <- df %>%
  filter(year <= 2017) %>%
  group_by(hs6, importer) %>%
  summarise(base_size = mean(exports, na.rm = TRUE), .groups = "drop") %>%
  mutate(size_tercile = ntile(base_size, 3))

df <- df %>% left_join(corridor_size, by = c("hs6", "importer"))
rm(corridor_size); gc()

run_tercile_es <- function(t) {
  fepois(
    exports ~ i(year, tariff_rate, ref = 2017) + preus_bin:year |
      hs6^importer + importer^year + hs2^year,
    data = filter(df, size_tercile == t),
    cluster = ~ hs6 + importer, fixef.tol = PPML_TOL
  )
}
m_es_t1 <- run_tercile_es(1)   # smallest corridors
m_es_t2 <- run_tercile_es(2)
m_es_t3 <- run_tercile_es(3)   # largest corridors

par(mfrow = c(1, 3)) # re-establish the layout cleanly
iplot(m_es_t1, ref.line = TRUE, main = "Small corridors",  ylim = c(-1.5, 2.5)); abline(h=0, lty=2, col="grey50")
iplot(m_es_t2, ref.line = TRUE, main = "Medium corridors", ylim = c(-1.5, 2.5)); abline(h=0, lty=2, col="grey50")
iplot(m_es_t3, ref.line = TRUE, main = "Large corridors",  ylim = c(-1.5, 2.5)); abline(h=0, lty=2, col="grey50")
par(mfrow = c(1, 1))

# Corridor-sizes: 

## 3b. Pre-US-share heterogeneity (the diversion mechanism) ----
# pre-US-share now in TREATMENT role (effect modifier), as event study,
# pre-trend shown openly. Reads: did formerly-US-dependent goods diverge,
# and was it already underway pre-2018?
m_es_het <- fepois(
  exports ~ i(year, tariff_rate, ref = 2017) +
    i(year, pre_us_share, ref = 2017) |
    hs6^importer + importer^year + hs2^year,
  data = df, cluster = ~ hs6 + importer, fixef.tol = PPML_TOL
)
# i.select = 2 -> plot the pre_us_share x year path (the heterogeneity term)
par(mfrow = c(1, 2))
iplot(m_es_het, i.select = 1, ref.line = TRUE, main = "Tariff x year",
      ylab = "Coef. (rel. 2017)", ylim = c(-1, 2)); abline(h=0, lty=2, col="grey50")
iplot(m_es_het, i.select = 2, ref.line = TRUE, main = "Pre-US-share x year",
      ylab = "Coef. (rel. 2017)"); abline(h=0, lty=2, col="grey50")
par(mfrow = c(1, 1))

# Corridor-size terciles (mean pre-2017 value, '000 USD): cuts at ~13 and ~176.
# Value shares: small 0.04%, medium 0.7%, large 99.3%. Trade is hugely
# concentrated in large corridors; small ones carry ~nothing and are pure noise
# (see wide CIs in small-corridor event study) -> justifies aggregating minor
# destinations into RoW. Corridor skew = why; top-100 importer cut (97.8%) = how.

# ============================================================
# Aggregated panel: top-100 destinations + ROW (ranked pre-shock)
# ============================================================
# Built from a clean copy of the main panel WITHOUT the Tier 3 corridor
# columns, so the aggregation key list is the only thing that defines df100.

df_base100 <- readRDS(file.path(output_path, "df_hs12.rds")) %>%
  filter(importer != 842) %>%
  left_join(
    readRDS(file.path(output_path, "df_hs12.rds")) %>%
      filter(year >= 2015, year <= 2017) %>%
      group_by(hs6) %>%
      summarise(
        us_exports_pre    = sum(exports[importer == 842], na.rm = TRUE),
        world_exports_pre = sum(exports, na.rm = TRUE),
        .groups = "drop"
      ) %>%
      mutate(pre_us_share = us_exports_pre / world_exports_pre) %>%
      select(hs6, pre_us_share),
    by = "hs6"
  ) %>%
  mutate(
    pre_us_share = replace_na(pre_us_share, 0),
    preus_bin = factor(
      case_when(
        pre_us_share == 0    ~ "0",
        pre_us_share <= 0.10 ~ "Low US exposure",
        pre_us_share > 0.10  ~ "High US exposure"
      ),
      levels = c("0", "Low US exposure", "High US exposure")
    )
  )

# rank destinations on pre-shock years (2015-2017)
imp_rank <- df_base100 %>%
  filter(year >= 2015, year <= 2017) %>%
  group_by(importer) %>%
  summarise(v = sum(exports), .groups = "drop") %>%
  mutate(share = v / sum(v)) %>%
  arrange(desc(share))

keep100 <- imp_rank %>% slice_max(share, n = 100) %>% pull(importer)
cat("top 100 cum share:",
    round(sum(imp_rank$share[imp_rank$importer %in% keep100]), 3), "\n")

keep100 #reasonable list of kept vs dropped.

df100 <- df_base100 %>%
  mutate(importer_grp = ifelse(importer %in% keep100, as.character(importer), "ROW")) %>%
  group_by(hs6, hs2, importer_grp, year, post2018, tariff_rate,
           preus_bin, pre_us_share) %>%
  summarise(exports = sum(exports, na.rm = TRUE), .groups = "drop") %>%
  mutate(log_exports = log(exports + 1))   # +1 to match the build's log definition

stopifnot(min(df100$exports, na.rm = TRUE) > 0)   # confirm no zero cells after aggregation
rm(df_base100); gc()

# ---- pooled estimates: no control / US control / US treatment ----
# no control
p100_nc <- fepois(exports ~ tariff_rate:post2018 |
                    hs6^importer_grp + importer_grp^year + hs2^year,
                  data = df100, cluster = ~ hs6 + importer_grp, fixef.tol = PPML_TOL)
o100_nc <- feols(log_exports ~ tariff_rate:post2018 |
                   hs6^importer_grp + importer_grp^year + hs2^year,
                 data = df100, cluster = ~ hs6 + importer_grp)

# pre-US as CONTROL (:year)
p100_ctrl <- fepois(exports ~ tariff_rate:post2018 + preus_bin:year |
                      hs6^importer_grp + importer_grp^year + hs2^year,
                    data = df100, cluster = ~ hs6 + importer_grp, fixef.tol = PPML_TOL)
o100_ctrl <- feols(log_exports ~ tariff_rate:post2018 + preus_bin:year |
                     hs6^importer_grp + importer_grp^year + hs2^year,
                   data = df100, cluster = ~ hs6 + importer_grp)

# pre-US as TREATMENT (triple interaction)
p100_trt <- fepois(exports ~ tariff_rate:post2018 + tariff_rate:post2018:pre_us_share |
                     hs6^importer_grp + importer_grp^year + hs2^year,
                   data = df100, cluster = ~ hs6 + importer_grp, fixef.tol = PPML_TOL)
o100_trt <- feols(log_exports ~ tariff_rate:post2018 + tariff_rate:post2018:pre_us_share |
                    hs6^importer_grp + importer_grp^year + hs2^year,
                  data = df100, cluster = ~ hs6 + importer_grp)

etable(
  "PPML no ctrl" = p100_nc, "OLS no ctrl"  = o100_nc,
  "PPML US ctrl" = p100_ctrl, "PPML US trt" = p100_trt,
  "OLS US ctrl"  = o100_ctrl, "OLS US trt"  = o100_trt,
  drop = "preus_bin", digits = 3, se.below = TRUE, fitstat = ~ n
)


## event study: control not treatment
es_p100 <- fepois(
  exports ~ i(year, tariff_rate, ref = 2017) + preus_bin:year |
    hs6^importer_grp + importer_grp^year + hs2^year,
  data = df100, cluster = ~ hs6 + importer_grp, fixef.tol = PPML_TOL
)
es_o100 <- feols(
  log_exports ~ i(year, tariff_rate, ref = 2017) + preus_bin:year |
    hs6^importer_grp + importer_grp^year + hs2^year,
  data = df100, cluster = ~ hs6 + importer_grp
)
par(mfrow = c(1, 2))
iplot(es_p100, ref.line = TRUE, main = "PPML (top 100)", ylim = c(-1, 2))
abline(h = 0, lty = 2, col = "grey50")
iplot(es_o100, ref.line = TRUE, main = "OLS (top 100)", ylim = c(-1, 2))
abline(h = 0, lty = 2, col = "grey50")
par(mfrow = c(1, 1))

## event study: as treatment not control

es_het100 <- fepois(
  exports ~ i(year, tariff_rate, ref = 2017) +
    i(year, pre_us_share, ref = 2017) |
    hs6^importer_grp + importer_grp^year + hs2^year,
  data = df100, cluster = ~ hs6 + importer_grp, fixef.tol = PPML_TOL
)
par(mfrow = c(1, 2))
iplot(es_het100, i.select = 1, ref.line = TRUE, main = "Tariff x year (top 100)", ylim = c(-1, 2))
abline(h = 0, lty = 2, col = "grey50")
iplot(es_het100, i.select = 2, ref.line = TRUE, main = "Pre-US-share x year (top 100)")
abline(h = 0, lty = 2, col = "grey50")
par(mfrow = c(1, 1))

## take out covid from treatment 
es_het100_nocovid <- fepois(
  exports ~ i(year, tariff_rate, ref = 2017) + i(year, pre_us_share, ref = 2017) |
    hs6^importer_grp + importer_grp^year + hs2^year,
  data = filter(df100, !year %in% c(2020, 2021)),
  cluster = ~ hs6 + importer_grp, fixef.tol = PPML_TOL
)
iplot(es_het100_nocovid, i.select = 2, ref.line = TRUE,
      main = "Pre-US-share x year, no COVID (top 100)")
abline(h = 0, lty = 2, col = "grey50")

# (a) hs6-only clustering on the RoW baseline (treatment is assigned at hs6)
es_p100_h6 <- summary(es_p100, cluster = ~ hs6)
iplot(es_p100_h6, ref.line = TRUE, main = "PPML top100, cluster hs6", ylim = c(-1,2)); abline(h=0,lty=2,col="grey50")
es_p100_h6

es_p100_h6_noctrl <- fepois(
  exports ~ i(year, tariff_rate, ref = 2017) |
    hs6^importer_grp + importer_grp^year + hs2^year,
  data = df100, cluster = ~ hs6
)
coeftable(es_p100_h6_noctrl)


######
# Final baseline: PPML, top-100 + RoW, saturated FE, hs6-clustered, no control
m_base <- fepois(
  exports ~ tariff_rate:post2018 |
    hs6^importer_grp + importer_grp^year + hs2^year,
  data = df100, cluster = ~ hs6, fixef.tol = 1e-6
)

# OLS companion, same spec
m_base_ols <- feols(
  log_exports ~ tariff_rate:post2018 |
    hs6^importer_grp + importer_grp^year + hs2^year,
  data = df100, cluster = ~ hs6
)

etable(
  "PPML (baseline)" = m_base,
  "OLS (companion)" = m_base_ols,
  digits = 3, se.below = TRUE, fitstat = ~ n + r2
)
