#!/usr/bin/env Rscript
# Underside-only RustLab measurements. Side parameters are supplied by ALMA.
# Usage: Rscript Run_ALMA_Side_Rust_Bottom.R --config=/path/to/config.json
# Formulas: references/DLC-Gait-Analysis-main/Runway_Analysis.Rmd, sections
# 5, 6 and 10. No side-view RustLab calculations or comparison calculations.
suppressPackageStartupMessages({library(dplyr); library(tidyr); library(jsonlite)})
options(dplyr.summarise.inform=FALSE, digits=17)
args <- commandArgs(trailingOnly=TRUE)
config_arg <- grep('^--config=', args, value=TRUE)
if (length(config_arg) != 1L) stop('Provide exactly one --config=FILE argument.')
config <- fromJSON(sub('^--config=', '', config_arg), simplifyVector=FALSE)
FPS <- as.numeric(config$frame_rate)
if (!is.finite(FPS) || FPS <= 0) stop('Frame rate must be positive and finite.')
FULL_ID <- as.character(config$full_id)
MOUSE <- as.character(config$mouse)
DAY <- as.character(config$day)
SCALE <- if (is.null(config$bottom_pixels_per_cm)) NA_real_ else as.numeric(config$bottom_pixels_per_cm)
if (!is.na(SCALE) && (!is.finite(SCALE) || SCALE <= 0)) stop('Invalid bottom calibration.')
threshold <- as.numeric(config$stance_speed_threshold_px_frame)
max_speed <- as.numeric(config$maximum_tracking_speed_px_frame)
if (!is.finite(threshold) || threshold < 0 || !is.finite(max_speed) || max_speed <= threshold)
  stop('Invalid underside speed thresholds.')
output_dir <- config$output_dir
dir.create(output_dir, recursive=TRUE, showWarnings=FALSE)
bottom <- read.csv(config$bottom_coordinates, check.names=FALSE, na.strings=c('NA','NaN','nan',''))
bottom <- bottom %>%
  filter(is.finite(x_corr), is.finite(y_corr), is.finite(likelyhood),
         likelyhood >= as.numeric(config$likelihood_threshold)) %>%
  mutate(mouse=MOUSE, full_id=FULL_ID, day=DAY, time=source_frame*60/FPS,
         day_Num=as.numeric(gsub('[^0-9.]', '', DAY)),
         side=ifelse(grepl('right$',parameter),'right','left')) %>%
  arrange(parameter, source_frame)

# RustLab's native 7 px/frame stance rule and 100 px/frame tracking QC,
# configurable through the application. Gaps never create a displacement.
Speed_down_pre <- bottom %>%
  group_by(day, mouse, parameter, full_id) %>%
  mutate(speed=abs(x_corr-lag(x_corr, default=first(x_corr))),
         speed=ifelse(source_frame-lag(source_frame, default=first(source_frame)-1L)==1L,speed,NA_real_),
         phase_names=ifelse(speed > threshold,'swing','stance'),
         phase_numbers=cumsum(coalesce(phase_names != lag(phase_names, default=first(phase_names)),TRUE))) %>%
  filter(is.finite(speed)) %>%
  group_by(full_id, phase_numbers) %>% mutate(Max_speed=max(speed)) %>%
  filter(Max_speed < max_speed) %>%
  group_by(full_id) %>% mutate(Max_steps=max(phase_numbers)) %>%
  filter(Max_steps > 10) %>% ungroup()
Speed_down <- Speed_down_pre %>%
  filter(parameter %in% c('d-front-left','d-front-right','d-back-left','d-back-right'))
Speed_down_cycle <- Speed_down %>% filter(phase_names=='stance') %>%
  group_by(mouse, day, full_id, phase_numbers) %>%
  mutate(relative_time=time-min(time)) %>% ungroup()

empty_values <- function() data.frame(Parameter=character(),Value=double())
finite_median <- function(values) {
  values <- values[is.finite(values)]
  if (length(values)) median(values) else NA_real_
}
Cycle_duration <- Stride_length <- Stance_Swing_time <- empty_values()
if (nrow(Speed_down_cycle)) {
  # Original formulas, retaining RustLab's session median and within-phase SD.
  Cycle_duration <- Speed_down_cycle %>%
    group_by(mouse, day, full_id, phase_numbers, day_Num) %>%
    summarize(duration=max(relative_time)-min(relative_time), sd=sd(relative_time)) %>%
    group_by(full_id, mouse, day, day_Num) %>%
    summarize(avg_duration=median(duration)/60, duration_sd_diff=finite_median(sd)/60) %>%
    gather(Parameter, Value, avg_duration:duration_sd_diff)
  Stride_length <- Speed_down_cycle %>%
    group_by(mouse, day, day_Num, full_id, phase_numbers, side) %>%
    summarize(stride_length=max(x_corr)-min(x_corr), sd=sd(x_corr)) %>%
    group_by(full_id, mouse, day, day_Num) %>%
    summarize(avg_stride_length=median(stride_length)/SCALE,
              stride_length_sd_diff=finite_median(sd)/SCALE) %>%
    gather(Parameter, Value, avg_stride_length:stride_length_sd_diff)
  Stance_Swing_time <- Speed_down_cycle %>%
    group_by(mouse, day, full_id, phase_numbers, parameter, side, day_Num) %>%
    summarize(max=max(time), min=min(time)) %>% group_by(parameter) %>%
    mutate(stance_time=max-min, swing_time=min-lag(max,default=first(max))) %>%
    filter(phase_numbers != 0) %>% group_by(full_id, mouse, day, day_Num) %>%
    summarize(avg_stance_time=median(stance_time)/60, avg_swing_time=median(swing_time)/60) %>%
    gather(Parameter, Value, avg_stance_time:avg_swing_time)
}

coordination <- empty_values()
paws <- c(FL='d-front-left', FR='d-front-right', BL='d-back-left', BR='d-back-right')
if (all(paws %in% Speed_down$parameter)) {
  states <- Speed_down %>% select(source_frame,parameter,phase_names) %>%
    pivot_wider(names_from=parameter,values_from=phase_names) %>% drop_na()
  names(states)[match(paws,names(states))] <- names(paws)
  states <- states %>% filter(!(FL=='stance' & FR=='stance' & BL=='stance' & BR=='stance'))
  if (nrow(states)) coordination <- data.frame(
    Parameter=c('FLBR_RATIO','FRBL_RATIO'),
    Value=c(mean(states$FL != states$BR), mean(states$FR != states$BL)))
}

# Original underside paw-to-body-center atan2 angles: 95th / 10th percentile,
# and arithmetic mean. Missing center/forepaw coordinates remain missing.
angle_rows <- list()
for (joint in c('LB','LF','RB','RF')) {
  paw <- switch(joint,LB='d-back-left',LF='d-front-left',RB='d-back-right',RF='d-front-right')
  center <- if (joint %in% c('LB','RB')) 'd-center-back' else 'd-center-front'
  paw_data <- Speed_down_pre[Speed_down_pre$parameter==paw,c('source_frame','x_corr','y_corr')]
  center_data <- Speed_down_pre[Speed_down_pre$parameter==center,c('source_frame','x_corr','y_corr')]
  values <- merge(paw_data,center_data,by='source_frame',suffixes=c('.paw','.center'))
  if (!nrow(values)) next
  angle <- abs(atan2(values$y_corr.paw-values$y_corr.center,
                    values$x_corr.paw-values$x_corr.center)*180/pi)
  angle <- ifelse(angle > 90,angle-90,angle)
  angle_rows[[length(angle_rows)+1L]] <- data.frame(
    Parameter=paste(joint,c('max_Angle','min_Angle','avg_Angle'),sep='__'),
    Value=c(unname(quantile(angle,.95)),unname(quantile(angle,.1)),mean(angle)))
}
measure_names <- c('FLBR_RATIO','FRBL_RATIO','avg_duration','duration_sd_diff',
                   'avg_stride_length','stride_length_sd_diff','avg_stance_time','avg_swing_time',
                   paste(rep(c('LB','LF','RB','RF'),3),
                         rep(c('max_Angle','min_Angle','avg_Angle'),each=4),sep='__'))
computed <- bind_rows(coordination,Cycle_duration,Stride_length,Stance_Swing_time,bind_rows(angle_rows))
all_raw_data <- data.frame(full_id=FULL_ID,day=DAY,mouse=MOUSE,Measure=measure_names,
  Value=computed$Value[match(measure_names,computed$Parameter)],
  ParameterGroup=c(rep('SynchrCycle_downPersp',8),rep('Angles_downPersp',12)),
  stringsAsFactors=FALSE)
stopifnot(nrow(all_raw_data)==20L, !anyDuplicated(all_raw_data$Measure))

# Each ALMA session statistic is a participant-level Measure/Value row, so the
# original RustLab schema needs no extra columns. Every stride is included;
# missing measurements do not contribute, and a singleton SD stays NA.
alma_rows <- list()
for (side in c('left','right')) {
  table <- read.csv(config$alma_csvs[[side]],check.names=FALSE,na.strings=c('NA','NaN','nan',''))
  for (parameter in unlist(config$alma_parameters)) {
    if (!parameter %in% names(table)) stop(paste('Missing ALMA column:',parameter))
    values <- suppressWarnings(as.numeric(table[[parameter]]))
    values <- values[is.finite(values)]
    statistics <- c(mean=if (length(values)) mean(values) else NA_real_,sd=sd(values))
    alma_rows[[length(alma_rows)+1L]] <- data.frame(full_id=FULL_ID,day=DAY,mouse=MOUSE,
      Measure=paste(side,parameter,names(statistics),sep='__'),Value=unname(statistics),
      ParameterGroup='ALMA_sidePersp',stringsAsFactors=FALSE)
  }
}
all_raw_data <- bind_rows(all_raw_data,bind_rows(alma_rows))
# Original RustLab summary schema and participant aggregation, unchanged.
all_sum_data <- all_raw_data %>% group_by(day,Measure,ParameterGroup) %>%
  summarize(Mean=mean(Value),median=median(Value),sd=sd(Value),sem=sd(Value)/sqrt(length(Value)))
# Keep write.csv defaults: quoted strings, R row names, and unquoted NA.
write.csv(all_raw_data,file.path(output_dir,'all_raw_data.csv'),na='NA')
write.csv(all_sum_data,file.path(output_dir,'all_summarized_data.csv'),na='NA')
cat('Exported 20 RustLab underside measures and',length(alma_rows)*2L,'ALMA session statistics.\n')
