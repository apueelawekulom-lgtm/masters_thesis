# ============================================================
# Transformation Stage Heterogeneity
# ============================================================

# Assumes:
#   df100
#   class12
#
# Later:
# df100   <- readRDS(...)
# class12 <- readRDS(...)

# ============================================================
# 1. Merge stage classifications
# ============================================================

df100_stage <- df100 %>%
  left_join(
    class12 %>% select(hs6, stage_group),
    by = "hs6"
  ) %>%
  mutate(
    stage_group = factor(
      stage_group,
      levels = c("S1", "S2", "S3", "S4", "S5"),
      ordered = TRUE
    )
  ) %>%
  filter(!is.na(stage_group))

table(df100_stage$stage_group, useNA = "ifany")

# ============================================================
# 2. PPML
# ============================================================

m_ppml_stage <- fepois(
  exports ~
    tariff_rate:post2018 +
    i(stage_group, I(tariff_rate * post2018), ref = "S1") +
    preus_bin:year |
    hs6^importer_grp +
    importer_grp^year +
    hs2^year,
  data = df100_stage,
  cluster = ~ hs6 + importer_grp,
  fixef.tol = PPML_TOL
)

# ============================================================
# 3. OLS
# ============================================================

m_ols_stage <- feols(
  log_exports ~
    tariff_rate:post2018 +
    i(stage_group, I(tariff_rate * post2018), ref = "S1") +
    preus_bin:year |
    hs6^importer_grp +
    importer_grp^year +
    hs2^year,
  data = df100_stage,
  cluster = ~ hs6 + importer_grp
)

# ============================================================
# 4. Results
# ============================================================

etable(
  "PPML" = m_ppml_stage,
  "OLS"  = m_ols_stage,
  drop = "preus_bin",
  digits = 3,
  se.below = TRUE,
  fitstat = ~ n
)

# Stage distribution

df100_stage %>%
  distinct(hs6, stage_group) %>%
  count(stage_group) %>%
  mutate(share = n / sum(n))



###

etable(
  m_ppml_stage,
  keep = "stage_group"
)


############### treatment on subsamples re: us exposure 


df_high_us <- df100_stage %>%
  filter(preus_bin == "High US exposure")

df_low_us <- df100_stage %>%
  filter(preus_bin == "Low US exposure")

# ============================================================
# High US exposure products (>10%)
# ============================================================

p100_stage_high <- fepois(
  exports ~
    tariff_rate:post2018 +
    i(stage_group, I(tariff_rate * post2018), ref = "S1") |
    hs6^importer_grp +
    importer_grp^year +
    hs2^year,
  data = df_high_us,
  cluster = ~ hs6 + importer_grp,
  fixef.tol = PPML_TOL
)

o100_stage_high <- feols(
  log_exports ~
    tariff_rate:post2018 +
    i(stage_group, I(tariff_rate * post2018), ref = "S1") |
    hs6^importer_grp +
    importer_grp^year +
    hs2^year,
  data = df_high_us,
  cluster = ~ hs6 + importer_grp
)
# ============================================================
# Low US exposure (0–10%)
# ============================================================

p100_stage_low <- fepois(
  exports ~
    tariff_rate:post2018 +
    i(stage_group, I(tariff_rate * post2018), ref = "S1") |
    hs6^importer_grp +
    importer_grp^year +
    hs2^year,
  data = df_low_us,
  cluster = ~ hs6 + importer_grp,
  fixef.tol = PPML_TOL
)

o100_stage_low <- feols(
  log_exports ~
    tariff_rate:post2018 +
    i(stage_group, I(tariff_rate * post2018), ref = "S1") |
    hs6^importer_grp +
    importer_grp^year +
    hs2^year,
  data = df_low_us,
  cluster = ~ hs6 + importer_grp
)

etable(
  "PPML High US" = p100_stage_high,
  "PPML Low US"  = p100_stage_low,
  "OLS High US"  = o100_stage_high,
  "OLS Low US"   = o100_stage_low,
  digits = 3,
  se.below = TRUE,
  fitstat = ~ n
)

etable(
  "PPML High US" = p100_stage_high,
  "PPML Low US"  = p100_stage_low,
  keep = "stage_group",
  digits = 3,
  se.below = TRUE
)



# ============================================================
# Stage-specific event studies
# ============================================================

run_stage_es <- function(stage){
  
  fepois(
    exports ~
      
      i(
        year,
        I(tariff_rate * (stage_group == stage)),
        ref = 2017
      ) +
      
      preus_bin:year |
      
      hs6^importer_grp +
      importer_grp^year +
      hs2^year,
    
    data = df100_stage,
    cluster = ~ hs6 + importer_grp,
    fixef.tol = PPML_TOL
  )
  
}

es_s2 <- run_stage_es("S2")
es_s3 <- run_stage_es("S3")
es_s4 <- run_stage_es("S4")
es_s5 <- run_stage_es("S5")


#plot
par(mfrow = c(2,2))

iplot(es_s2,
      ref.line = TRUE,
      main = "S2",
      ylim = c(-2, 4))
abline(h = 0, lty = 2, col = "grey50")

iplot(es_s3,
      ref.line = TRUE,
      main = "S3",
      ylim = c(-2, 4))
abline(h = 0, lty = 2, col = "grey50")

iplot(es_s4,
      ref.line = TRUE,
      main = "S4",
      ylim = c(-2, 4))
abline(h = 0, lty = 2, col = "grey50")

iplot(es_s5,
      ref.line = TRUE,
      main = "S5",
      ylim = c(-2, 4))
abline(h = 0, lty = 2, col = "grey50")

par(mfrow = c(1,1))
