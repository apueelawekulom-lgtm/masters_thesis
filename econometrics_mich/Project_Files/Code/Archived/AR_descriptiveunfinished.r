# =========================================
# MONTHLY HS6 EXPORTS: CHINA
# =========================================

library(tidyverse)
library(comtradr)
library(lubridate)

# =========================================
# COMTRADE API
# =========================================

Sys.setenv("COMTRADE_PRIMARY" = "YOUR_API_KEY")

# =========================================
# MONTHLY PULL: CHINA EXPORTS
# =========================================

target_partners <- c("USA", "World")
episode_years   <- c(2018:2020, 2024:2025)

safe_monthly <- function(partner, year) {
  
  tryCatch({
    
    message("Pulling: ", partner, " - ", year)
    
    Sys.sleep(1.2)
    
    ct_get_data(
      reporter       = "CHN",
      partner        = partner,
      flow_direction = "Export",
      start_date     = year,
      end_date       = year,
      frequency      = "M",
      commodity_classification = "HS",
      commodity_code = "everything"
    )
    
  }, error = function(e) {
    
    message("Failed: ", partner, " - ", year)
    NULL
    
  })
  
}

df_monthly_raw <- expand_grid(
  partner = target_partners,
  year = episode_years
) %>%
  pmap(~ safe_monthly(..1, ..2)) %>%
  bind_rows()

# =========================================
# CLEAN MONTHLY DATA
# =========================================

df_monthly <- df_monthly_raw %>%
  filter(
    aggr_level == 6,
    !is.na(cmd_code)
  ) %>%
  mutate(
    hs6 = str_pad(as.character(cmd_code), 6, pad = "0"),
    year = ref_year,
    month = ref_month,
    date = as.Date(paste(year, month, "01", sep = "-")),
    exports = primary_value
  ) %>%
  select(
    hs6,
    partner_iso,
    partner_desc,
    year,
    month,
    date,
    exports
  )

# =========================================
# MERGE BEC CLASSIFICATION
# =========================================

BEC_path <- file.path(data_path, "PLAID_v0.1_bec_H0.csv")

BEC <- read.csv(BEC_path)

BEC_clean <- BEC %>%
  select(hs6_code, bec) %>%
  rename(hs6 = hs6_code) %>%
  mutate(hs6 = as.character(hs6))

df_bec <- df_monthly %>%
  left_join(BEC_clean, by = "hs6") %>%
  mutate(
    bec_group = recode(
      bec,
      "capital" = "Capital",
      "consumption" = "Consumer",
      "intermediate" = "Intermediate"
    )
  ) %>%
  filter(!is.na(bec_group))

# =========================================
# CREATE US VS NON-US DESTINATIONS
# =========================================

world_monthly <- df_bec %>%
  filter(partner_iso == "W00") %>%
  group_by(
    year,
    month,
    date,
    hs6,
    bec_group
  ) %>%
  summarise(
    world_exports = sum(exports, na.rm = TRUE),
    .groups = "drop"
  )

us_monthly <- df_bec %>%
  filter(partner_iso == "USA") %>%
  group_by(
    year,
    month,
    date,
    hs6,
    bec_group
  ) %>%
  summarise(
    us_exports = sum(exports, na.rm = TRUE),
    .groups = "drop"
  )

monthly_trade <- world_monthly %>%
  left_join(
    us_monthly,
    by = c("year", "month", "date", "hs6", "bec_group")
  ) %>%
  mutate(
    us_exports = replace_na(us_exports, 0),
    nonus_exports = world_exports - us_exports
  )

# =========================================
# AGGREGATE TO BEC GROUP LEVEL
# =========================================

plot_data <- monthly_trade %>%
  group_by(date, bec_group) %>%
  summarise(
    us_exports = sum(us_exports, na.rm = TRUE),
    nonus_exports = sum(nonus_exports, na.rm = TRUE),
    .groups = "drop"
  ) %>%
  pivot_longer(
    cols = c(us_exports, nonus_exports),
    names_to = "destination",
    values_to = "exports"
  ) %>%
  mutate(
    destination = recode(
      destination,
      "us_exports" = "US",
      "nonus_exports" = "Non-US"
    )
  )

# =========================================
# INDEX EXPORTS (JAN 2018 = 100)
# =========================================

plot_data <- plot_data %>%
  group_by(bec_group, destination) %>%
  mutate(
    base_value = exports[date == as.Date("2018-01-01")][1],
    export_index = 100 * exports / base_value
  ) %>%
  ungroup()

# =========================================
# PLOT
# =========================================

ggplot(
  plot_data %>%
    filter(bec_group %in% c("Consumer", "Intermediate")),
  aes(
    x = date,
    y = export_index,
    colour = destination
  )
) +
  geom_line(linewidth = 1.1) +
  facet_wrap(~ bec_group, scales = "free_y") +
  geom_vline(
    xintercept = as.Date("2018-07-01"),
    linetype = "dashed"
  ) +
  scale_x_date(
    date_labels = "%Y",
    date_breaks = "1 year"
  ) +
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


