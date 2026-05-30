# ============================================================
# CLASSIFICATION OVERLAP:
# UNCTAD SOP vs BEC vs CUSTOM STAGES
#
# Goal:
# Compare conceptual overlap between:
# - UNCTAD SOP
# - BEC
# - Custom transformation stages
#
# IMPORTANT:
# This is NOT the regression concordance.
#
# For this exercise:
# HS17 custom classifications are concorded to HS92,
# because SOP/BEC are naturally HS92-based.
# ============================================================

root <- "/Users/michelleshi/Documents/BSE/Term 3/Thesis/Project_Files"
data_path   <- file.path(root, "Data")
output_path <- file.path(root, "Output")

library(dplyr)
library(stringr)
library(readxl)
library(data.table)

# ============================================================
# 1. Paths
# ============================================================

conc92_path <- file.path(
  data_path,
  "HS2017toHS1992.xlsx"
)

# ============================================================
# 2. Load Custom HS17 Classifications
# ============================================================

class17 <- fread(stage_path)

class17 <- class17 %>%
  
  mutate(
    
    hs17 = str_pad(
      as.character(code),
      6,
      pad = "0"
    ),
    
    stage_group = case_when(
      
      setfit_class %in% c(1,2,3) ~ "S1_3",
      
      setfit_class == 4 ~ "S4",
      
      setfit_class == 5 ~ "S5",
      
      TRUE ~ NA_character_
    )
  )

# ============================================================
# 3. Load HS17 -> HS92 Concordance
# ============================================================

conc92 <- read_excel(conc92_path)

names(conc92) <- c("hs17", "hs92")

conc92 <- conc92 %>%
  
  mutate(
    
    hs17 = str_pad(
      as.character(hs17),
      6,
      pad = "0"
    ),
    
    hs92 = str_pad(
      as.character(hs92),
      6,
      pad = "0"
    )
  )

# ============================================================
# 4. Concordance Diagnostics
# ============================================================

# HS17 -> multiple HS92? No; all one to one
conc92 %>%
  count(hs17) %>%
  filter(n > 1)

# Multiple HS17 -> same HS92? Yes; expected 
conc92 %>%
  count(hs92) %>%
  filter(n > 1)

#Check how much the multiple HS17 matters
class92_check <- class17 %>%
  
  left_join(conc92, by = "hs17") %>%
  
  group_by(hs92) %>%
  
  summarise(
    n_stage = n_distinct(stage_group),
    stages = paste(sort(unique(stage_group)), collapse = ", "),
    n = n(),
    .groups = "drop"
  )

# HS92 codes with multiple stage assignments
class92_check %>%
  filter(n_stage > 1)

# Distribution
table(class92_check$n_stage) #only 13 conflicts! of 5000+! looks good

# ============================================================
# 5. Convert Custom Classifications to HS92
# ============================================================

# If multiple HS17 codes map into one HS92 code,
# keep the classification with highest confidence.

class92 <- class17 %>%
  
  left_join(
    conc92,
    by = "hs17"
  ) %>%
  
  group_by(hs92) %>%
  
  slice_max(
    order_by = setfit_confidence,
    n = 1,
    with_ties = FALSE
  ) %>%
  
  ungroup()

# ============================================================
# 6. Restrict to HS72+
# ============================================================

# Focus on manufacturing-heavy product groups

class92 <- class92 %>%
  filter(as.numeric(substr(hs92, 1, 2)) >= 72)

# ============================================================
# 7. Load UNCTAD SOP
# ============================================================

sop_raw <- read_xlsx(sop_path)

sop_clean <- sop_raw %>%
  
  filter(
    ProductGroup != "Total",
    ProductDescription != "UN Special Code"
  ) %>%
  
  transmute(
    
    hs92 = str_pad(
      as.character(ProductCode),
      6,
      pad = "0"
    ),
    
    sop = ProductGroupDescription
  ) %>%
  
  distinct()

# Restrict to HS72+
sop_clean <- sop_clean %>%
  filter(as.numeric(substr(hs92, 1, 2)) >= 72)

# ============================================================
# 8. Load BEC
# ============================================================

bec_raw <- read.csv(bec_path)

bec_clean <- bec_raw %>%
  
  transmute(
    
    hs92 = str_pad(
      as.character(hs6_code),
      6,
      pad = "0"
    ),
    
    bec
  )

# Restrict to HS72+
bec_clean <- bec_clean %>%
  filter(as.numeric(substr(hs92, 1, 2)) >= 72)

# ============================================================
# 9. Merge All Three Systems
# ============================================================

compare_df <- class92 %>%
  
  select(
    hs92,
    stage_group,
    setfit_confidence
  ) %>%
  
  left_join(
    sop_clean,
    by = "hs92"
  ) %>%
  
  left_join(
    bec_clean,
    by = "hs92"
  )

# ============================================================
# 10. Coverage Diagnostics
# ============================================================

n_distinct(compare_df$hs92)

mean(is.na(compare_df$sop))
mean(is.na(compare_df$bec))
mean(is.na(compare_df$stage_group)) #good coverage, only a little of SOP missing

# ============================================================
# 11. OUR STAGES vs UNCTAD SOP
# ============================================================

table(compare_df$stage_group, compare_df$sop)

# Row shares
prop.table(
  table(compare_df$stage_group, compare_df$sop),
  margin = 1
)

# ============================================================
# 12. OUR STAGES vs BEC
# ============================================================

table(compare_df$stage_group, compare_df$bec)

prop.table(
  table(compare_df$stage_group, compare_df$bec),
  margin = 1
)

# ============================================================
# 13. UNCTAD SOP vs BEC
# ============================================================

table(compare_df$sop, compare_df$bec)

prop.table(
  table(compare_df$sop, compare_df$bec),
  margin = 1
)


# ============================================================
# 14. Summary Shares
# ============================================================

compare_df %>%
  
  group_by(stage_group, sop) %>%
  
  summarise(
    n = n(),
    .groups = "drop"
  ) %>%
  
  group_by(stage_group) %>%
  
  mutate(
    share = n / sum(n)
  ) %>%
  
  arrange(
    stage_group,
    desc(share)
  )
