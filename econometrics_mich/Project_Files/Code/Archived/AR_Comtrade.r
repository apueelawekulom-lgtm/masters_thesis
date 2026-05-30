### =========================================
### UN COMTRADE PRESENTATION 2
### =========================================

# install.packages("comtradr")

library(tidyverse)
library(comtradr)

Sys.setenv("COMTRADE_PRIMARY" = "0ca5ca6ac9a7420da8039828de48501c")

# comtradr accepts "everything" for all partners
test_annual <- ct_get_data(
  reporter       = "USA",
  partner        = partner,
  flow_direction = "import",
  start_date     = 2025,
  end_date       = 2025,
  commodity_code = "TOTAL"
)
nrow(test_annual) #so works with 'every'thing'

# =========================================
# TABLE OF TOP MOVERS
# =========================================

# World totals for share denominator
world_totals <- df_annual_all %>%
  filter(partner_iso == "W00", aggr_level == 0) %>%
  select(period, world_value = primary_value)

# Rank ALL countries in both years
ranked_2018 <- df_annual_all %>%
  filter(aggr_level == 0, !partner_iso %in% c("W00", "_X", NA), period == 2018) %>%
  arrange(desc(primary_value)) %>%
  mutate(rank_2018 = row_number()) %>%
  select(partner_iso, partner_desc, rank_2018, value_2018 = primary_value)

ranked_2024 <- df_annual_all %>%
  filter(aggr_level == 0, !partner_iso %in% c("W00", "_X", NA), period == 2024) %>%
  arrange(desc(primary_value)) %>%
  mutate(rank_2024 = row_number()) %>%
  select(partner_iso, partner_desc, rank_2024, value_2024 = primary_value)

# Join all, then filter to top 30 by 2024 rank
rankings <- ranked_2018 %>%
  full_join(ranked_2024, by = c("partner_iso", "partner_desc")) %>%
  mutate(
    world_2018 = world_totals$world_value[world_totals$period == 2018],
    world_2024 = world_totals$world_value[world_totals$period == 2024],
    share_2018 = value_2018 / world_2018,
    share_2024 = value_2024 / world_2024,
    pct_change = (value_2024 - value_2018) / value_2018,
    difference = rank_2018 - rank_2024,
    mover      = !is.na(difference) & difference > 3
  ) %>%
  filter(rank_2024 <= 30) %>%
  arrange(rank_2024) %>%
  select(partner_iso, partner_desc, rank_2018, rank_2024, difference,
         share_2018, share_2024, value_2018, value_2024, pct_change, mover)

write.csv(rankings, "~/Desktop/rankings.csv", row.names = FALSE)

##Formatting

#install.packages("gt")
#library(gt)

rankings %>%
  select(-mover) %>%
  gt() %>%
  fmt_percent(columns = c(share_2018, share_2024, pct_change), decimals = 1) %>%
  tab_style(
    style = cell_fill(color = "#d4edda"),
    locations = cells_body(rows = mover == TRUE)
  )

# =========================================
# MONTHLY PULL: TARGET PARTNERS + WORLD
# =========================================

target_partners <- c("CHN", "MEX", "VNM", "S19", "THA", "World")
episode_years   <- c(2018:2020, 2024:2025)

safe_monthly <- function(partner, year) {
  tryCatch({
    message("Pulling: ", partner, " - ", year)
    Sys.sleep(1.2)
    ct_get_data(
      reporter       = "USA",
      partner        = partner,
      flow_direction = "Import",
      start_date     = year,
      end_date       = year,
      frequency      = "M",
      commodity_code = "TOTAL"
    )
  }, error = function(e) { message("Failed: ", partner, year); NULL })
}

df_monthly_raw <- expand_grid(partner = target_partners, year = episode_years) %>%
  pmap(~ safe_monthly(..1, ..2)) %>%
  bind_rows()

#colnames(df_monthly_raw)

# =========================================
# CLEAN + SHARES
# =========================================

# Helper: extract year, month, date from raw pull
parse_months <- function(df) df %>%
  filter(aggr_level == 0) %>%
  mutate(year  = ref_year,
         month = ref_month,
         date  = as.Date(paste(year, month, "01", sep = "-")))

# Separate world (denominator) and partner (numerator) series
world <- df_monthly_raw %>%
  filter(partner_iso == "W00") %>%
  parse_months() %>%
  select(date, year, month, world_value = primary_value)

partners <- df_monthly_raw %>%
  filter(partner_iso != "W00") %>%
  parse_months() %>%
  select(date, year, month, partner_iso, primary_value)

# RoW = world total minus sum of selected partners
row <- partners %>%
  left_join(world, by = c("date", "year", "month")) %>%
  group_by(date, year, month) %>%
  summarise(primary_value = first(world_value) - sum(primary_value),
            world_value   = first(world_value), .groups = "drop") %>%
  mutate(partner_iso = "RoW")

# Combine, compute shares, apply episode date filters
df_shares <- partners %>%
  left_join(world, by = c("date", "year", "month")) %>%
  bind_rows(row) %>%
  mutate(share = primary_value / world_value) %>%
  filter(!(year == 2020 & month > 2),   # ep1: cut at Feb 2020 (pre-COVID)
         !(year == 2024 & month < 11))  # ep2: start Nov 2024 (post-election)


df_shares %>% group_by(date) %>% summarise(total_share = sum(share))


# =========================================
# CHART: PARTNER SHARES OF US IMPORTS
# =========================================

# Labels for facets and legend
episode_labels <- c("ep1" = "Episode 1: 2018 Section 301 Tariffs",
                    "ep2" = "Episode 2: 2025 Liberation Day Tariffs")

country_labels <- c(CHN = "China", MEX = "Mexico", VNM = "Vietnam",
                    S19 = "Taiwan", THA = "Thailand", RoW = "Rest of World")

country_colours <- c(CHN = "#e41a1c", MEX = "#377eb8", VNM = "#4daf4a",
                     S19 = "#984ea3", THA = "#ff7f00", RoW = "grey70")

df_shares %>%
  # Assign episode and months-since-start for aligned x-axis
  mutate(
    episode      = ifelse(year <= 2020, "ep1", "ep2"),
    months_since = ifelse(episode == "ep1",
                          (year - 2018) * 12 + month - 1,
                          (year - 2024) * 12 + month - 11)
  ) 

# =========================================
# CHART 1: SHARE LEVELS (no RoW)
# =========================================

df_plot <- df_shares %>%
  mutate(
    episode      = ifelse(year <= 2020, "ep1", "ep2"),
    months_since = ifelse(episode == "ep1",
                          (year - 2018) * 12 + month - 1,
                          (year - 2024) * 12 + month - 11)
  )
# Chart 1 with real dates
vline_df <- data.frame(date = as.Date("2025-04-02"), episode = "ep2")

df_shares %>%
  filter(partner_iso != "RoW") %>%
  mutate(episode = ifelse(year <= 2020, "ep1", "ep2")) %>%
  ggplot(aes(x = date, y = share, colour = partner_iso)) +
  geom_line(linewidth = 0.8) +
  geom_vline(data = vline_df, aes(xintercept = date), linetype = "dashed", colour = "black") +
  facet_wrap(~ episode, labeller = as_labeller(episode_labels), scales = "free_x") +
  coord_cartesian(ylim = c(0, 0.25)) +
  scale_x_date(date_labels = "%b-%y", date_breaks = "3 months") +
  scale_y_continuous(labels = scales::percent_format(accuracy = 1)) +
  scale_colour_manual(values = country_colours, labels = country_labels) +
  labs(x = NULL, y = "Share of US imports", colour = NULL,
       title  = "Partner shares of US imports: tariff episodes compared",
       caption = "Source: UN Comtrade. Episode 1: Jan 2018–Feb 2020. Episode 2: Nov 2024–Dec 2025. Dashed line: Liberation Day (Apr 2025).") +
  theme_minimal() +
  theme(legend.position = "bottom",
        axis.text.x = element_text(angle = 45, hjust = 1))

# =========================================
# CHART 2: PP CHANGE FROM EPISODE START (with RoW)
# =========================================

# Build df_shares_chart2 with Thailand absorbed into RoW
row_chart2 <- partners %>%
  filter(partner_iso != "THA") %>%
  left_join(world, by = c("date", "year", "month")) %>%
  group_by(date, year, month) %>%
  summarise(primary_value = first(world_value) - sum(primary_value),
            world_value   = first(world_value), .groups = "drop") %>%
  mutate(partner_iso = "RoW")

df_shares_chart2 <- partners %>%
  filter(partner_iso != "THA") %>%
  left_join(world, by = c("date", "year", "month")) %>%
  bind_rows(row_chart2) %>%
  mutate(share = primary_value / world_value) %>%
  filter(!(year == 2020 & month > 2),
         !(year == 2024 & month < 11)) %>%
  mutate(episode = ifelse(year <= 2020, "ep1", "ep2"))

# Plot — real dates on x-axis, Liberation Day annotation on ep2
vline_df <- data.frame(date = as.Date("2025-04-02"), episode = "ep2")

df_shares_chart2 %>%
  group_by(episode, partner_iso) %>%
  mutate(share_change = share - first(share)) %>%
  ggplot(aes(x = date, y = share_change, colour = partner_iso)) +
  geom_line(linewidth = 0.8) +
  geom_hline(yintercept = 0, linetype = "dashed", colour = "grey50") +
  geom_vline(data = vline_df, aes(xintercept = date), linetype = "dashed", colour = "black") +
  facet_wrap(~ episode, labeller = as_labeller(episode_labels), scales = "free_x") +
  coord_cartesian(ylim = c(-0.12, 0.08)) +
  scale_x_date(date_labels = "%b-%y", date_breaks = "3 months") +
  scale_y_continuous(labels = scales::percent_format(accuracy = 1)) +
  scale_colour_manual(values = country_colours, labels = country_labels) +
  labs(x = NULL, y = "Change in share (pp)",
       colour = NULL,
       title  = "Change in partner shares of US imports: tariff episodes compared",
       caption = "Source: UN Comtrade. Episode 1: Jan 2018–Feb 2020. Episode 2: Nov 2024–Dec 2025. Dashed line: Liberation Day (Apr 2025).") +
  theme_minimal() +
  theme(legend.position = "bottom",
        axis.text.x = element_text(angle = 45, hjust = 1))


# ============================================================
# 1. Merge BEC categories onto main panel
# ============================================================

BEC_path <- file.path(data_path, "PLAID_v0.1_bec_H4.csv") 

BEC <- read.csv(BEC_path) 

BEC_clean <- BEC %>% select(hs6_code, bec) %>% rename(hs6 = hs6_code) %>% 
  mutate(hs6 = as.character(hs6))

df_bec <- df %>%
  left_join(BEC_clean, by = "hs6")

# Quick check
table(df_bec$bec, useNA = "ifany")

bec_shares <- df_bec %>%
  group_by(bec) %>%
  summarise(
    exports = sum(exports, na.rm = TRUE),
    .groups = "drop"
  ) %>%
  mutate(
    share = exports / sum(exports)
  )

bec_shares

# ============================================================
# 2. Clean BEC groups
# ============================================================

# =========================================
# MONTHLY HS6 PULL: CHINA EXPORTS
# =========================================

head(df_monthly_raw)


df_monthly <- df_monthly_raw %>%
  mutate(
    bec_group = case_when(
      bec == "capital" ~ "Capital",
      bec == "consumption" ~ "Consumer",
      bec == "intermediate" ~ "Intermediate",
      TRUE ~ NA_character_
    )
  ) %>%
  filter(!is.na(bec_group))

table(df_monthly$bec_group)

# ============================================================
# 3. Aggregate exports by group and destination
# ============================================================

monthly_plot <- df_bec %>%
  mutate(
    us_dest = ifelse(importer == 842, "US", "Non-US")
  ) %>%
  group_by(year, month, bec_group, us_dest) %>%
  summarise(
    exports = sum(primary_value, na.rm = TRUE),
    .groups = "drop"
  )

colnames(df_bec)

# ============================================================
# 4. Create date + restrict window
# ============================================================

monthly_plot <- monthly_plot %>%
  filter(
    year >= 2017,
    year <= 2025
  ) %>%
  mutate(
    date = as.Date(paste(year, month, "01", sep = "-"))
  )

# ============================================================
# 5. Index exports (=100 in Jan 2018)
# ============================================================

monthly_plot <- monthly_plot %>%
  group_by(bec_group, us_dest) %>%
  mutate(
    base_value = exports[date == as.Date("2018-01-01")][1],
    export_index = 100 * exports / base_value
  ) %>%
  ungroup()

# ============================================================
# 6. Plot
# ============================================================

ggplot(
  monthly_plot %>%
    filter(bec_group %in% c("Consumer", "Intermediate")),
  aes(
    x = date,
    y = export_index,
    colour = us_dest
  )
) +
  geom_line(linewidth = 1.1) +
  facet_wrap(~ bec_group, scales = "free_y") +
  geom_vline(
    xintercept = as.Date("2018-07-01"),
    linetype = "dashed"
  ) +
  scale_x_date(date_labels = "%Y") +
  labs(
    title = "Chinese Export Diversion by Product Type",
    subtitle = "Indexed exports (Jan 2018 = 100)",
    x = NULL,
    y = "Export index",
    colour = NULL
  ) +
  theme_minimal() +
  theme(
    legend.position = "bottom"
  )