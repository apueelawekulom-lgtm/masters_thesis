library(yaml)

# Works regardless of where the script sits in the folder tree
ROOT <- here::here()  # install.packages("here") if needed

PATHS <- yaml::read_yaml(file.path(ROOT, "config/paths.yaml"))

# Helper function — equivalent of the Python get()
get_path <- function(chapter, key) {
  file.path(ROOT, PATHS[[chapter]][[key]])
}
