### ============================================================
### APPENDIX / DATA VALIDATION & ROBUSTNESS CHECKS
### ============================================================

root <- "/Users/michelleshi/Documents/BSE/Term 3/Thesis/Project_Files"
source("code/01_Regressions.R")

# ============================================================
# 1. Tariff structure sanity checks
# ============================================================

# Check distribution of tariff intensity
tariff_hs6 %>% summarise(
  min = min(tariff_rate, na.rm = TRUE),
  max = max(tariff_rate, na.rm = TRUE),
  mean = mean(tariff_rate, na.rm = TRUE)
)

# Check whether tariff series is constant within HS6 (it should be)
tariff_hs6 %>%
  group_by(hs6) %>%
  summarise(n_unique = n_distinct(tariff_rate)) %>%
  count(n_unique)

# Confirm max vs time consistency (internal consistency check)
check <- tariff_hs6 %>%
  group_by(hs6) %>%
  summarise(
    max_rate = max(tariff_rate, na.rm = TRUE),
    t1_value = tariff_rate[1],
    .groups = "drop"
  )

check %>% summarise(agreement = mean(max_rate == t1_value, na.rm = TRUE))


# ============================================================
# 2. Coverage of HS6 in tariff data vs BACI
# ============================================================

baci_hs6 <- df %>% distinct(hs6) %>% pull(hs6)
tariff_hs6_list <- tariff_hs6 %>% pull(hs6)

length(setdiff(baci_hs6, tariff_hs6_list))   # missing from tariff data
length(intersect(baci_hs6, tariff_hs6_list)) # overlap


# HS2 structure of missing codes (diagnostic for selection bias)
missing_hs6 <- setdiff(baci_hs6, tariff_hs6_list)

df %>%
  filter(hs6 %in% missing_hs6) %>%
  distinct(hs6, hs2) %>%
  count(hs2, sort = TRUE) #1036 missing from Fajgelbaum. maybe ghost HS codes.


# ============================================================
# 3. Comparison to Bown tariff dataset
# ============================================================

bown_tariffs <- read_dta(file.path(data_path,
                                   "Bown-TrumpTariffs-CHN-hs6.dta"))

bown_clean <- bown_tariffs %>%
  rename(hs6 = hs06) %>%
  mutate(
    bown_treated = as.integer(
      pmax(TT301_a, TT301_b, TT301_c, TT301_d, TT301_e, TT301_f,
           na.rm = TRUE) > 0
    )
  ) %>%
  select(hs6, bown_treated)

# Overlap structure
compare <- tariff_hs6 %>%
  full_join(bown_clean, by = "hs6") %>%
  mutate(
    in_faj = !is.na(tariff_rate),
    in_bown = !is.na(bown_treated)
  )

compare %>% count(in_faj, in_bown) #Bown did have tariffs for about 250. 


# ============================================================
# 4. Missing tariff universe diagnostics
# ============================================================

missing_from_faj <- setdiff(baci_hs6, tariff_hs6_list)

missing_in_bown <- intersect(missing_from_faj, bown_clean$hs6)
missing_in_neither <- setdiff(missing_from_faj, bown_clean$hs6)

length(missing_in_bown)
length(missing_in_neither)


# HS structure of “ghost” codes (not in either dataset)
df %>%
  filter(hs6 %in% missing_in_neither) %>%
  distinct(hs6, hs2) %>%
  count(hs2, sort = TRUE)


# ============================================================
# 5. Sample composition checks
# ============================================================

df %>%
  summarise(
    n_hs6 = n_distinct(hs6),
    n_treated_hs6 = n_distinct(hs6[tariff_rate > 0]),
    share_rows_treated = mean(tariff_rate > 0)
  )


# ============================================================
# 6. FE robustness checks
# ============================================================

m_old_fe <- feols(
  log_exports ~ tariff_rate:post2018 | hs6 + importer + year,
  data = df %>% filter(year >= 2014),
  cluster = ~hs6
)

m_new_fe <- feols(
  log_exports ~ tariff_rate:post2018 | hs6^importer + importer^year,
  data = df %>% filter(year >= 2014),
  cluster = ~hs6
)

etable(m_old_fe, m_new_fe,
       headers = c("Old FE", "High-Dimensional FE"))


# ============================================================
# 7. Event study robustness
# ============================================================

reg_es <- feols(
  log_exports ~ i(year, tariff_rate, ref = 2017) |
    hs6^importer + importer^year,
  data = df,
  cluster = ~hs6
)

iplot(reg_es)


# ============================================================
# 8. BEC vs GVC measurement comparison
# ============================================================

BEC <- read.csv(BEC_path)
GVC <- read.csv(GVC_path)

# Harmonise HS6
BEC <- BEC %>% mutate(hs6 = as.character(hs6_code))

GVC <- GVC %>%
  mutate(
    hs6 = as.character(subheading),
    gvc_broad = case_when(
      nli_label == "Final Good" ~ "consumption",
      nli_label == "Intermediate Assembly/Capital" ~ "capital",
      TRUE ~ "intermediate"
    )
  )

# Merge
merged <- BEC %>%
  select(hs6, bec) %>%
  left_join(GVC %>% select(hs6, nli_label, gvc_broad), by = "hs6")

# Coverage + agreement
mean(!is.na(merged$nli_label))          # coverage rate
mean(merged$bec == merged$gvc_broad, na.rm = TRUE)  # agreement rate


# Cross-tab structure
merged %>%
  count(bec, gvc_broad) %>%
  group_by(bec) %>%
  mutate(share = n / sum(n))


# Distribution comparison
prop.table(table(BEC$bec))
prop.table(table(GVC$nli_label))
prop.table(table(GVC$gvc_broad))


# Summary distribution table
dist_table <- full_join(
  BEC %>%
    count(category = bec) %>%
    mutate(BEC = n / sum(n)) %>%
    select(category, BEC),
  
  GVC %>%
    count(category = gvc_broad) %>%
    mutate(GVC = n / sum(n)) %>%
    select(category, GVC),
  
  by = "category"
)

dist_table



# Summary stats
summary(tariff_hs6$tariff_rate)

# Or more detail
tariff_hs6 %>%
  summarise(
    n = n(),
    min = min(tariff_rate),
    mean = mean(tariff_rate),
    median = median(tariff_rate),
    max = max(tariff_rate),
    share_zero = mean(tariff_rate == 0)
  )

hist(tariff_hs6$tariff_rate, breaks = 30)
