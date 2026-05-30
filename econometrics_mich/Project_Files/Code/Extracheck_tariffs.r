# ============================================================
# Diagnostic: split genuine (matched) zeros from assumed (imputed) zeros
# Does NOT reprocess BACI. Regenerates only the tariff lookup (Section 2)
# and checks code membership against the saved df_hs12.rds.
# ============================================================

library(dplyr); library(tidyr); library(stringr); library(haven); library(concordance)

root        <- "/Users/michelleshi/Documents/BSE/Term 3/Thesis/Project_Files"
data_path   <- file.path(root, "Data")
output_path <- file.path(root, "Output")
tariff_path <- file.path(data_path, "Fajgelbaum-z_usch_w.dta")

# ------------------------------------------------------------
# 1. Regenerate the tariff lookup (Section 2 of the build only)
# ------------------------------------------------------------
tariff_hs17 <- read_dta(tariff_path) %>%
  filter(t == 1) %>%                                  # post-shock period
  mutate(hs6 = str_pad(as.character(hs6), 6, pad = "0")) %>%
  transmute(hs17 = hs6, tariff_rate = dz_usch_w)

# how many genuine zeros exist in the SOURCE (pre-merge)?
cat("\n--- source (tariff_hs17) ---\n")
print(summary(tariff_hs17$tariff_rate))
cat("rows:           ", nrow(tariff_hs17), "\n")
cat("source zeros:   ", sum(tariff_hs17$tariff_rate == 0), "\n")
cat("source zero %:  ", round(mean(tariff_hs17$tariff_rate == 0), 4), "\n")

# concord HS17 -> HS12 (matches the build)
tariff_hs12 <- tariff_hs17 %>%
  mutate(hs6 = concord_hs(sourcevar = hs17, origin = "HS5",
                          destination = "HS4", dest.digit = 6, all = FALSE)) %>%
  filter(!is.na(hs6))

cat("concorded HS12 codes:", n_distinct(tariff_hs12$hs6), "\n")

# ------------------------------------------------------------
# 2. Load saved panel + reconstruct match status via %in%
# ------------------------------------------------------------
df_hs12 <- readRDS(file.path(output_path, "df_hs12.rds")) %>%
  mutate(in_tariff = hs6 %in% tariff_hs12$hs6)        # TRUE = matched to tariff data

# ------------------------------------------------------------
# 3. The split (observation level)
# ------------------------------------------------------------
cat("\n--- zero split, OBSERVATION level ---\n")
split_obs <- df_hs12 %>%
  summarise(
    n_rows       = n(),
    all_zero     = sum(tariff_rate == 0),
    assumed_zero = sum(!in_tariff),                       # unmatched = imputed
    genuine_zero = sum(tariff_rate == 0 & in_tariff)      # matched, measured 0
  ) %>%
  mutate(
    assumed_share_obs = assumed_zero / n_rows,
    check_reconciles  = (assumed_zero + genuine_zero) == all_zero
  )
print(split_obs)

cat("\n--- zero split, DISTINCT hs6 level ---\n")
split_hs6 <- df_hs12 %>%
  distinct(hs6, in_tariff, tariff_rate) %>%
  summarise(
    n_codes        = n_distinct(hs6),
    assumed_codes  = n_distinct(hs6[!in_tariff]),
    genuine_zero_codes = n_distinct(hs6[tariff_rate == 0 & in_tariff])
  )
print(split_hs6)

cat("\n--- zero split, TRADE-VALUE share ---\n")
split_val <- df_hs12 %>%
  summarise(
    total_exports   = sum(exports, na.rm = TRUE),
    assumed_exports = sum(exports[!in_tariff], na.rm = TRUE)
  ) %>%
  mutate(assumed_share_value = assumed_exports / total_exports)
print(split_val)

# ------------------------------------------------------------
# 4. Sanity check: any MATCHED code that is zero in the panel
#    but NONZERO in the lookup? (would signal a merge/concordance problem)
# ------------------------------------------------------------
cat("\n--- merge sanity (should be 0 rows) ---\n")
merge_problem <- df_hs12 %>%
  filter(tariff_rate == 0, in_tariff) %>%
  distinct(hs6) %>%
  inner_join(tariff_hs12, by = "hs6") %>%
  filter(tariff_rate != 0)
cat("matched codes zero-in-panel but nonzero-in-lookup:", nrow(merge_problem), "\n")
# if >0, inspect: print(merge_problem)

# ------------------------------------------------------------
# 5. OPTIONAL: write corrected flag back into the saved panel
#    (no BACI reprocessing). Uncomment to run.
# ------------------------------------------------------------
# df_hs12 <- readRDS(file.path(output_path, "df_hs12.rds")) %>%
#   mutate(imputed_zero = !(hs6 %in% tariff_hs12$hs6))   # TRUE = assumed/imputed zero
# saveRDS(df_hs12, file.path(output_path, "df_hs12.rds"))
# cat("\nPatched imputed_zero into df_hs12.rds\n")