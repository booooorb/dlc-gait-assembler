# Adapted HINDLIMB-ONLY RustLab1 R analysis, supplied with GX10564.
# Application integration parameterizes recording inputs and filter coefficients.
# Measurement and aggregation expressions retain the supplied R arithmetic.
# The full 106-row catalog is retained. Forelimb and fore/hind ratios are NA by scope.
# This is the user-authorized adapted run, not the untouched RustLab1 analysis.
# Original Runway_Analysis.Rmd and source DLC CSVs are never modified.
# Measurements below use original RustLab1 arithmetic and aggregation, with
# explicit changes to input cleaning, range exclusions and baseline handling.
# Rscript Run_GMM_Adapted_RustLab1.R --output-dir=/path/to/results
# Optional: --data-dir=... --timing-file=... --repo-root=... --python=...
# --diagnostics-dir=... saves verification intermediates outside the result folder.
# --no-stickplots skips only the plotting section, not any R measurement.
suppressPackageStartupMessages({library(dplyr);library(tidyr);library(jsonlite)})
options(dplyr.summarise.inform=FALSE, digits=17)
argv <- commandArgs(trailingOnly=TRUE)
option <- function(key,default) {
  hit <- argv[startsWith(argv,paste0('--',key,'='))]
  if(length(hit))substring(hit[[1]],nchar(key)+4L) else default
}
script_arg <- commandArgs()[startsWith(commandArgs(),'--file=')]
script_dir <- if(length(script_arg))dirname(normalizePath(gsub('~+~',' ',sub('^--file=','',script_arg[[1]]),fixed=TRUE))) else getwd()
config_file <- option('config','')
config <- if(nzchar(config_file))jsonlite::fromJSON(config_file,simplifyVector=FALSE) else list()
setting <- function(key,default){
  if(!key %in% names(config))return(default)
  if(is.null(config[[key]]))NA_real_ else config[[key]]
}
data_dir <- option('data-dir',getwd())
output_dir <- option('output-dir',script_dir)
timing_file <- option('timing-file',file.path(script_dir,'Stride_detection.csv'))
repo_root <- option('repo-root',getwd())
python <- option('python',Sys.which('python'))
diagnostics_dir <- option('diagnostics-dir',tempfile('gx10564_adapted_'))
dir.create(output_dir,recursive=TRUE,showWarnings=FALSE)
dir.create(diagnostics_dir,recursive=TRUE,showWarnings=FALSE)
FPS <- as.numeric(setting('frame_rate',239.76))
NFRAMES <- as.integer(setting('frame_count',1135L))
PIXELS_PER_CM <- as.numeric(setting('pixels_per_cm',31.3667))
STRIDE_PIXELS_PER_CM <- as.numeric(setting('stride_pixels_per_cm',31.37))
SIDE_SCALES <- setting('side_scales',list(left=PIXELS_PER_CM,right=PIXELS_PER_CM))
side_scale <- function(side)vapply(as.character(side),function(s){
  value<-SIDE_SCALES[[s]];if(is.null(value))NA_real_ else as.numeric(value)
},numeric(1))
MAX_INTERNAL_GAP <- as.integer(setting('maximum_coordinate_gap_frames',11L))
FULL_ID <- as.character(setting('full_id','recording'))
MOUSE <- as.character(setting('mouse','unknown'))
DAY <- as.character(setting('day','unknown'))
DAY_NUM <- suppressWarnings(as.numeric(gsub('[^0-9.]','',DAY)))

# 1. Existing Speed GMM stride detection --------------------------------------
# Preserve the previous detector's phases and accepted cycles exactly.
# Its likelihood >=0.5 and 6-Hz preprocessing are not changed by this run.
# Parameter coordinates below have NO likelihood or camera-ROI rejection.
phase_labels <- read.csv(timing_file,stringsAsFactors=FALSE,check.names=FALSE)
required <- c('source_frame','parameter','phase_names','trusted','cycle_id')
stopifnot(identical(names(phase_labels),required))
# HINDLIMB SCOPE: remove forepaw timings before every calculation and export.
phase_labels<-phase_labels[phase_labels$parameter %in% c('d-back-left','d-back-right'),]
stopifnot(nrow(phase_labels)==2L*NFRAMES)
phase_labels$trusted <- as.logical(phase_labels$trusted)
cycle_list <- lapply(sort(unique(na.omit(phase_labels$cycle_id))),function(id){
  d <- phase_labels[!is.na(phase_labels$cycle_id)&phase_labels$cycle_id==id,]
  d <- d[order(d$source_frame),]
  stopifnot(length(unique(d$parameter))==1L,all(diff(d$source_frame)==1L),all(d$trusted))
  a<-min(d$source_frame);b<-max(d$source_frame)+1L
  swings<-d$source_frame[d$phase_names=='swing'];stopifnot(length(swings)>0)
  toeoff<-min(swings);paw<-d$parameter[[1]]
  data.frame(cycle_id=id,parameter=paw,side=sub('.*-','',paw),
    limb=if(grepl('-back-',paw))'back' else 'front',
    start_frame=a,end_frame_inclusive=b-1L,next_touchdown_frame=b,toeoff_frame=toeoff,
    cycle_duration_seconds=(b-a)/FPS,stance_duration_seconds=(toeoff-a)/FPS,
    swing_duration_seconds=(b-toeoff)/FPS,full_id=FULL_ID,mouse=MOUSE,day=DAY,
    day_Num=DAY_NUM,phase_numbers=id,stance_time=(toeoff-a)*60/FPS,
    swing_time=(b-toeoff)*60/FPS,seconds=(b-a)/FPS)
})
canonical <- bind_rows(cycle_list)
if(!nrow(canonical))canonical<-data.frame(cycle_id=integer(),parameter=character(),
  start_frame=integer(),end_frame_inclusive=integer(),cycle_duration_seconds=double())
if(!'--preview-only' %in% argv){
  minimum<-as.integer(setting('minimum_complete_strides',1L))
  for(paw in c('d-back-left','d-back-right'))if(sum(canonical$parameter==paw)<minimum)
    stop(paste('Not enough complete Speed GMM strides for',paw,'(minimum',minimum,')'))
}
cycle_vector <- function(paw){
  d<-phase_labels[phase_labels$parameter==paw,];d<-d[order(d$source_frame),]
  stopifnot(identical(as.integer(d$source_frame),0:(NFRAMES-1L)))
  d$cycle_id
}

# 2. Raw DLC loading and short coordinate-gap repair --------------------------
# Keep every finite X/Y value regardless of likelihood. No movement-based
# outlier replacement, amplitude clipping or extrapolation is performed.
# Only genuinely absent coordinates may be linearly filled, at most 11 frames,
# with finite endpoints INSIDE THE SAME accepted GMM cycle. Long/edge gaps stay NA.
repair_short_gaps <- function(values,ids){
  x<-as.numeric(values);x[!is.finite(x)]<-NA_real_;changed<-rep(FALSE,length(x))
  runs<-rle(is.na(x));ends<-cumsum(runs$lengths);starts<-ends-runs$lengths+1L
  for(k in which(runs$values)){
    a<-starts[k];b<-ends[k]
    if(a<=1L||b>=length(x)||b-a+1L>MAX_INTERNAL_GAP)next
    own<-ids[(a-1L):(b+1L)]
    if(anyNA(own)||length(unique(own))!=1L)next
    x[a:b]<-approx(c(a-1L,b+1L),x[c(a-1L,b+1L)],xout=a:b)$y
    changed[a:b]<-TRUE
  }
  list(values=x,interpolated=changed)
}

# 3. BUTTERWORTH SMOOTHING: ALMA settings and exact algorithm -----------------
# Enabled for X and Y, before RustLab1 distances, excursions or angles.
# ALMA source: src/dlc_gait_assembly/runway/manual/gait_analysis/business/
#              alma/alma_signal_filter.py, butterworth_filter().
# Its implementation is scipy.signal.butter(5, cutoff/(FPS/2), 'low') followed
# by scipy.signal.filtfilt(b,a,coordinates). We use the SAME 5th-order 6-Hz
# coefficients at 239.76 FPS and the SAME forward/backward, steady-state initial
# conditions and 18-frame odd-reflection padding, implemented below in R.
# Two passes give zero phase shift (effective 10th-order magnitude response).
# Coefficients are specific to this recording's fixed FPS and 6-Hz cutoff.
# There is no smoothing across unfilled gaps. Finite runs <=18 frames retain
# their actual supplied coordinates because filtfilt padding is unavailable.
# No smoothed value is rejected because of amplitude, sign or likelihood.
BUTTERWORTH_ENABLED <- TRUE
BUTTERWORTH_ORDER <- 5L
BUTTERWORTH_CUTOFF_HZ <- as.numeric(setting('filter_cutoff',6))
BUTTERWORTH_PADLEN <- 18L
BUTTER_B <- c(2.3521794397853945e-06,1.1760897198926973e-05,
             2.3521794397853946e-05,2.3521794397853946e-05,
             1.1760897198926973e-05,2.3521794397853945e-06)
BUTTER_A <- c(1,-4.491322588487604,8.09227322659324,-7.309728725778051,
             3.3096622222019914,-0.6008088647875054)
BUTTER_ZI <- c(0.999997647836134,-3.4913367016186156,4.600913003306254,
              -2.708839244380034,0.600811216976302)
if(!is.null(config$filter_b)){
  BUTTER_B<-as.numeric(unlist(config$filter_b));BUTTER_A<-as.numeric(unlist(config$filter_a))
  BUTTER_ZI<-as.numeric(unlist(config$filter_zi))
}
stopifnot(FPS>0,BUTTERWORTH_CUTOFF_HZ>0,BUTTERWORTH_CUTOFF_HZ<FPS/2,
          length(BUTTER_B)==6L,length(BUTTER_A)==6L,length(BUTTER_ZI)==5L)
iir_forward <- function(x,state){
  output<-numeric(length(x));m<-length(state)
  for(i in seq_along(x)){
    y<-BUTTER_B[1L]*x[i]+state[1L];output[i]<-y
    for(j in seq_len(m-1L))state[j]<-state[j+1L]+BUTTER_B[j+1L]*x[i]-BUTTER_A[j+1L]*y
    state[m]<-BUTTER_B[m+1L]*x[i]-BUTTER_A[m+1L]*y
  }
  output
}
alma_filtfilt_R <- function(x){
  n<-length(x);p<-BUTTERWORTH_PADLEN;stopifnot(n>p,all(is.finite(x)))
  extended<-c(2*x[1L]-rev(x[2L:(p+1L)]),x,
              2*x[n]-rev(x[(n-p):(n-1L)]))
  forward<-iir_forward(extended,BUTTER_ZI*extended[1L])
  backward<-iir_forward(rev(forward),BUTTER_ZI*forward[length(forward)])
  rev(backward)[(p+1L):(p+n)]
}
smooth_finite_runs <- function(x){
  result<-x
  if(!BUTTERWORTH_ENABLED)return(result)
  runs<-rle(is.finite(x));ends<-cumsum(runs$lengths);starts<-ends-runs$lengths+1L
  for(k in which(runs$values & runs$lengths>BUTTERWORTH_PADLEN)){
    rows<-starts[k]:ends[k];result[rows]<-alma_filtfilt_R(x[rows])
  }
  result
}
native<-list();smoothing_audit<-list();gap_masks<-list()
for(view in c('left','right','bottom')){
  files<-if(!is.null(config$input_files))as.character(config$input_files[[view]]) else
    list.files(file.path(data_dir,view),pattern='[.]csv$',full.names=TRUE)
  stopifnot(length(files)==1L)
  headers<-read.csv(files[[1]],header=FALSE,nrows=3,check.names=FALSE,stringsAsFactors=FALSE)
  bodyparts<-as.character(headers[2,]);axes<-as.character(headers[3,])
  aliases<-config$marker_mapping[[view]]
  if(!is.null(aliases))for(j in seq_along(bodyparts)){
    replacement<-aliases[[bodyparts[j]]]
    if(!is.null(replacement))bodyparts[j]<-as.character(replacement)
  }
  d<-read.csv(files[[1]],header=FALSE,skip=3,check.names=FALSE,stringsAsFactors=FALSE)
  stopifnot(nrow(d)==NFRAMES)
  columns<-list(source_frame=0:(NFRAMES-1L))
  allowed<-switch(view,left=c('toe','MTP','ankle','hip','iliac_crest','knee'),
                  right=c('back_toe','MTP','ankle','hip','iliac_crest','knee'),bottom=c('LH_paw','RH_paw'))
  for(marker in intersect(unique(bodyparts[-1L]),allowed)){
    limb<-'back'
    side<-if(view=='bottom')if(marker=='LH_paw')'left' else 'right' else view
    paw<-paste('d',limb,side,sep='-');ids<-cycle_vector(paw)
    for(axis in c('x','y','likelihood')){
      position<-which(bodyparts==marker & axes==axis);stopifnot(length(position)==1L)
      values<-as.numeric(d[[position]])
      key<-paste(marker,axis)
      if(axis=='likelihood'){columns[[key]]<-values;next}
      fixed<-repair_short_gaps(values,ids)
      processed<-smooth_finite_runs(fixed$values)
      columns[[key]]<-processed
      gap_masks[[paste(view,key)]]<-fixed$interpolated
      smoothing_audit[[length(smoothing_audit)+1L]]<-data.frame(view=view,marker=marker,axis=axis,
        original_missing=sum(!is.finite(values)),interpolated=sum(fixed$interpolated),
        remaining_missing=sum(!is.finite(processed)),finite_coordinates_retained=sum(is.finite(values)),
        smoothing_order=BUTTERWORTH_ORDER,cutoff_hz=BUTTERWORTH_CUTOFF_HZ)
      write.csv(data.frame(source_frame=0:(NFRAMES-1L),raw=values,repaired=fixed$values,smoothed=processed),
        file.path(diagnostics_dir,paste0('signal_',view,'_',marker,'_',axis,'.csv')),row.names=FALSE,na='NA')
    }
  }
  native[[view]]<-as.data.frame(columns,check.names=FALSE)
  write.csv(native[[view]],file.path(diagnostics_dir,paste0('native_',view,'.csv')),row.names=FALSE,na='NA')
}
write.csv(bind_rows(smoothing_audit),file.path(diagnostics_dir,'smoothing_audit.csv'),row.names=FALSE)
if('--preview-only' %in% argv){
  write.csv(canonical,file.path(diagnostics_dir,'canonical.csv'),row.names=FALSE,na='NA')
  write.csv(phase_labels,file.path(output_dir,'Stride_detection.csv'),row.names=FALSE,na='NA')
  quit(save='no',status=0L)
}

# 4. Map anatomical labels and coordinate convention -------------------------
# Left toe is a HIND toe. Right back_toe is hind; right front_toe is fore.
# Knee and MTP are used only for the stickplots, never as RustLab1 ankle/toe.
mapping<-list(left=c(toe='l-back-toe',ankle='l-back-ankle',hip='l-hip',iliac_crest='l-iliac-crest'),
  right=c(back_toe='r-back-toe',ankle='r-back-ankle',hip='r-hip',iliac_crest='r-iliac-crest'),
  bottom=c(LH_paw='d-back-left',RH_paw='d-back-right'))
parts<-list()
for(view in names(mapping))for(marker in names(mapping[[view]])){
  d<-native[[view]];y<-d[[paste(marker,'y')]]
  yy<-if(view=='left')1250+y else if(view=='right')250-y else 500+y
  parts[[length(parts)+1L]]<-data.frame(time=d$source_frame*60/FPS,x_corr=2704-d[[paste(marker,'x')]],
    y_corr=yy,likelyhood=d[[paste(marker,'likelihood')]],parameter=unname(mapping[[view]][[marker]]),
    mouse=MOUSE,day=DAY,full_id=FULL_ID,side=if(view=='bottom')'down' else view)
}
long_data<-bind_rows(parts)
# ALTERED: remove >0.95 confidence filter AND the original rig-specific ROI.
# All finite supplied coordinates are treated as real observations for this run.
long_data_clean<-long_data %>% filter(is.finite(x_corr),is.finite(y_corr))

# Original RustLab1 left-camera flip (Runway_Analysis.Rmd 175-178).
long_data_clean2 <- long_data_clean %>%
  mutate(y_corr2=ifelse(side=='left',y_corr*(-1)+1506,y_corr)) %>%
  select(-y_corr) %>% dplyr::rename(y_corr=y_corr2)
long_data_clean2$source_frame<-as.integer(round(long_data_clean2$time*FPS/60))

# 5. Exact GMM windows transferred to R inputs -------------------------------
speed_rows<-list();spatial_rows<-list();timing_rows<-list();side_rows<-list()
for(paw in unique(phase_labels$parameter)){
  own<-long_data_clean2[long_data_clean2$parameter==paw,]
  labels<-phase_labels[phase_labels$parameter==paw,]
  label_idx<-match(own$source_frame,labels$source_frame)
  own<-own[labels$trusted[label_idx],];label_idx<-match(own$source_frame,labels$source_frame)
  side<-sub('.*-','',paw);limb<-if(grepl('-back-',paw))'back' else 'front'
  own$side<-side;own$limb<-limb;own$phase_numbers<-labels$cycle_id[label_idx]
  own$phase_names<-labels$phase_names[label_idx]
  own$phase<-ifelse(own$phase_names=='stance',paw,NA_character_)
  own$day_Num<-DAY_NUM
  # Compatibility columns are removed by the original synchronization expression.
  # They do not create, replace or export any speed measurement.
  for(column in c('speed','Max_speed','Max_steps','Max_Time_in_phase','Max_speed_true','speed_true'))own[[column]]<-NA_real_
  speed_rows[[length(speed_rows)+1L]]<-own %>% select(-source_frame)
}
for(i in seq_len(nrow(canonical))){
  c<-canonical[i,];a<-c$start_frame;b<-c$next_touchdown_frame
  own<-long_data_clean2 %>% filter(parameter==c$parameter,source_frame>=a,source_frame<=b)
  own$phase_numbers<-c$cycle_id;own$side<-c$side;own$limb<-c$limb;own$day_Num<-7
  own$relative_time<-(own$source_frame-a)*60/FPS
  spatial_rows[[i]]<-own %>% select(-source_frame)
  timing_rows[[i]]<-data.frame(mouse=MOUSE,day=DAY,full_id=FULL_ID,side=c$side,limb=c$limb,
    phase_numbers=c$cycle_id,day_Num=DAY_NUM,time=(a:b)*60/FPS,relative_time=((a:b)-a)*60/FPS)
  geometry<-long_data_clean2 %>% filter(side==c$side,source_frame>=a,source_frame<b)
  geometry$limb<-c$limb;geometry$phase_numbers<-c$cycle_id
  side_rows[[i]]<-geometry %>% select(-source_frame)
}
Speed_down<-bind_rows(speed_rows)
Speed_down_cycle<-bind_rows(spatial_rows)
full_cycle_timing<-bind_rows(timing_rows)
vertical_df_steps<-bind_rows(side_rows) %>% mutate(y_rel=y_corr/side_scale(side))
vertical_df_steps$parameter_short<-gsub('l-|r-','',vertical_df_steps$parameter)

# Helpers evaluate original R aggregation stages after the GMM timing adapter.
pipe_parts<-function(x)if(is.call(x)&&identical(x[[1]],as.name('%>%')))c(pipe_parts(x[[2]]),list(x[[3]]))else list(x)
eval_steps<-function(data,steps,envir=parent.frame()){
  local<-new.env(parent=envir);local$.adapted_input<-data;call<-as.name('.adapted_input')
  for(step in steps)call<-as.call(list(as.name('%>%'),call,step))
  eval(call,envir=local)
}
summary_tail<-function(expression,data){
  steps<-pipe_parts(expression[[3]])[-1L]
  groups<-which(vapply(steps,function(x)is.call(x)&&identical(x[[1]],as.name('group_by')),logical(1)))
  eval_steps(data,steps[max(groups):length(steps)])
}
empty_joint_angles<-function()data.frame(full_id=character(),mouse=character(),day=character(),
  side=character(),limb=character(),time=double(),phase_numbers=integer(),Joints=character(),Angle=double())

# 6. RustLab1 parameter calculations -----------------------------------------
# The source-line comments identify the original formulas. ALTERED blocks are
# limited to authorized exclusions, absolute output, and GMM timing transfer.


# Original Runway_Analysis.Rmd lines 414-419 — ALTERED as noted below.
expr_Cycle_duration <- quote(
Cycle_duration <- full_cycle_timing %>% 
  group_by(mouse, day, full_id, phase_numbers, day_Num) %>%
  summarize(duration = max(relative_time)-min(relative_time), sd = sd(relative_time)) %>%
  group_by(full_id, mouse, day,day_Num) %>%
  summarize(avg_duration = median(duration)/60, duration_sd_diff= median(sd)/60)%>% # in seconds
  gather(Parameter, Value, avg_duration:duration_sd_diff) 
)
eval(expr_Cycle_duration)


# Original Runway_Analysis.Rmd lines 439-445.
expr_Stride_length <- quote(
Stride_length <- Speed_down_cycle %>% 
  group_by(mouse, day, day_Num,  full_id, phase_numbers, side) %>%
  summarize(stride_length = max(x_corr)-min(x_corr), sd=sd(x_corr)) %>%
  group_by(full_id, mouse, day, day_Num) %>%
  summarize(avg_stride_length = median(stride_length)/STRIDE_PIXELS_PER_CM, stride_length_sd_diff = median(sd)/STRIDE_PIXELS_PER_CM) %>% # in cm
  gather(Parameter, Value, avg_stride_length:stride_length_sd_diff) %>%
  drop_na()
)
eval(expr_Stride_length)


# Original Runway_Analysis.Rmd lines 463-471: GMM timings replace legacy phase differences; original final aggregation.
expr_Stance_Swing_time <- quote(
Stance_Swing_time <- Speed_down_cycle %>%
  group_by(mouse, day,full_id, phase_numbers, parameter, side, day_Num) %>%
  summarize(max = max(time, na.rm=T), min = min(time, na.rm = T)) %>%
  group_by(parameter) %>%
  mutate(stance_time = max-min, swing_time = min - lag(max, default = first(max))) %>%
  filter(phase_numbers != 0) %>%
  group_by(full_id, mouse, day,  day_Num) %>%
  summarize(avg_stance_time = median(stance_time)/60, avg_swing_time = median(swing_time)/60) %>%
  gather(Parameter, Value, avg_stance_time:avg_swing_time) 
)
Stance_Swing_time <- summary_tail(expr_Stance_Swing_time,canonical)


# Bottom-view body-center markers are genuinely absent. No center is invented.
summary_angle_down<-data.frame(full_id=character(),day=character(),joint=character(),Parameter=character(),Value=double())


# Original Runway_Analysis.Rmd lines 809-816.
expr_summary_vertical_analysis_df_stroked <- quote(
summary_vertical_analysis_df_stroked <-  vertical_df_steps %>%
  group_by(mouse, side, parameter_short, phase_numbers, full_id, day)  %>% # you do the calculation for every step
  mutate(y_max=max(y_corr), y_min=min(y_corr), mean = mean(y_corr)) %>% # Identify the highest, lowest, middle coordinate per step
  mutate(y_max_norm = y_max-y_min, mean_norm = mean - y_min, y_min_norm = y_min - y_min) %>%   # Relative heights per step
  group_by(mouse, side, parameter_short, full_id, day) %>%  # You calculate for all steps the parameters 
  mutate(Movement = median(y_max_norm), Average_Height = median(mean_norm), Baseline = median(y_min_norm)) %>%
  ungroup() %>%
  distinct(Movement, .keep_all = T)
)
eval(expr_summary_vertical_analysis_df_stroked)


# Original Runway_Analysis.Rmd lines 833-838 — ALTERED as noted below.
summary_summary_vertical_analysis_df_2 <- summary_vertical_analysis_df_stroked %>%
  gather(Measure, Value, Movement:Baseline)  %>%
  filter(Measure != "Baseline") %>% 
  group_by(full_id, mouse, side, parameter_short, parameter, day,Measure)%>%
  summarize(Value = median(Value)) # Remove 0 Values that you confirmed previously


# Original Runway_Analysis.Rmd lines 841-841.
summary_summary_vertical_analysis_df_2$day_Num <- as.numeric(gsub("[^0-9.]", "",  summary_summary_vertical_analysis_df_2$day))


# ALTERED: absolute measurement in mm. No missing day-0 value is subtracted.
# This is NOT a zero-filled baseline or a claim of change from day 0.
summary_summary_vertical_analysis_df_3 <- summary_summary_vertical_analysis_df_2 %>%
  mutate(Value=Value/side_scale(side)*10)


# Original Runway_Analysis.Rmd lines 892-900.
expr_horizontal_df <- quote(
horizontal_df <- vertical_df_steps %>% 
  group_by(mouse,full_id, day, limb, side, parameter_short, phase_numbers) %>%
  mutate(x_max = max(x_corr), x_min = min(x_corr), mean = mean(x_corr)) %>%
  mutate(Movement = x_max - x_min) %>%
  distinct(Movement, .keep_all = T) %>% # Collapse Elements 
  ungroup()%>%
  group_by(mouse,full_id, day, limb, side, parameter_short) %>%
  mutate(Average_Step_Size = median(Movement), Max_Step_Size = max(Movement), Min_Step_Size = min(Movement)) %>%
  distinct(Average_Step_Size, .keep_all = T) # Collapse the elements
)
eval(expr_horizontal_df)


# Original Runway_Analysis.Rmd lines 920-920.
horizontal_df_toe <- vertical_df_steps %>% filter(parameter_short %in% c("back-toe","front-toe-tip", "hip", "shoulder"))


# Original Runway_Analysis.Rmd lines 922-924.
hip_steps <- vertical_df_steps %>% 
   filter(parameter_short %in%  c("hip", "shoulder")) %>%
  select(time, side, limb, x_corr, parameter_short, mouse, full_id, day, phase_numbers)


# Original Runway_Analysis.Rmd lines 927-933 — ALTERED as noted below.
horizontal_df_steps <- left_join(hip_steps, horizontal_df_toe, by = c("full_id", "day", "mouse",  "side", "limb", "time", "phase_numbers")) %>%
  mutate(distance = x_corr.y - x_corr.x) %>%
  group_by(full_id, day, mouse, side, limb, parameter_short.y,parameter) %>%
  summarise(retraction = unname(quantile(distance, 0.05)), protraction = unname(quantile(distance, 0.95)), average=mean(distance), median = median(distance))%>%
  gather(Measure, Value, retraction:median) %>%
  filter(!(parameter_short.y %in% c("shoulder", "hip")))


# ALTERED: retain absolute signed toe-to-hip/shoulder distances in mm.
# The original -100 < Value < 60 pixel rejection and day-0 subtraction are removed.
new_hz_steps <- horizontal_df_steps %>% mutate(Value=Value/side_scale(side)*10)
new_hz_steps$day_Num <- DAY_NUM


# Original Runway_Analysis.Rmd lines 985-994: original final aggregation on complete canonical GMM durations.
expr_duration_steps <- quote(
duration_steps <- vertical_df_steps %>%
  group_by(full_id, day, mouse,  side,limb, phase_numbers) %>%
  summarize(duration = max(time)) %>%
  mutate(duration_minus = duration - lag(duration, default = first(duration))) %>%
  mutate(seconds = duration_minus/60) %>% # We imaged with 60 fps 
  filter(phase_numbers >=3 ) %>%
  group_by(full_id, day, mouse, side, limb) %>%
  summarize(seconds = median(seconds)) %>%
  unite(joint, side, limb, sep = "_", remove = F) %>%
  mutate(joint = factor(joint, levels = c("left_front", "left_back", "right_back", "right_front")))
)
keys<-unique(vertical_df_steps[,c('side','limb')])
available<-paste(canonical$side,canonical$limb) %in% paste(keys$side,keys$limb)
duration_steps<-summary_tail(expr_duration_steps,canonical[available,])


# Original Runway_Analysis.Rmd lines 1018-1026: original displacement arithmetic, with adjacency of actual GMM cycles.
expr_movement_per_step <- quote(
movement_per_step <- vertical_df_steps %>% 
  group_by(full_id,day, mouse, limb, side, phase_numbers, parameter_short) %>%
  summarize(x_corr = mean(x_corr)) %>%
  filter(parameter_short == "hip") %>% # reference to movement is the hip 
  group_by(full_id,day, mouse, limb, side, parameter_short) %>%
  mutate(x_corr_diff = x_corr - lag(x_corr, default = first(x_corr))) %>%
  filter(phase_numbers > 2) %>%
  group_by(full_id, day, mouse, side, limb) %>% # per video
  summarize(x_corr_diff = median(x_corr_diff))
)
steps<-pipe_parts(expr_movement_per_step[[3]])
gate<-which(vapply(steps,function(x)grepl('phase_numbers > 2',paste(deparse(x),collapse=' '),fixed=TRUE),logical(1)))
means<-eval_steps(vertical_df_steps,steps[2:(gate-1L)]) %>% ungroup()
keep<-rep(FALSE,nrow(means))
groups<-split(seq_len(nrow(means)),interaction(means$full_id,means$side,means$limb,means$parameter_short,drop=TRUE))
for(rows in groups){
  rows<-rows[order(means$phase_numbers[rows])]
  if(length(rows)<2L)next
  for(k in 2:length(rows)){
    previous<-canonical[canonical$cycle_id==means$phase_numbers[rows[k-1L]],]
    current<-canonical[canonical$cycle_id==means$phase_numbers[rows[k]],]
    keep[rows[k]]<-nrow(previous)==1L && nrow(current)==1L && previous$parameter==current$parameter &&
      previous$next_touchdown_frame==current$start_frame
  }
}
movement_per_step<-eval_steps(means[keep,],steps[(gate+1L):length(steps)])


# Original Runway_Analysis.Rmd lines 1048-1049.
vertical_analysis_df_stroked_angle <- filter(vertical_df_steps, parameter_short %in% c("wrist", "shoulder", "elbow", "front-toe-tip", "hip", "iliac-crest", "back-ankle", "back-toe")) %>%
  select(-c(likelyhood, y_rel))


# Original Runway_Analysis.Rmd lines 1056-1056.
test_left_x_ba <- vertical_analysis_df_stroked_angle %>%  filter(side == "left" & limb == "back")%>% select(-c(parameter, y_corr)) %>% spread(parameter_short, x_corr, convert = F)


# Original Runway_Analysis.Rmd lines 1057-1057.
test_left_y_ba <- vertical_analysis_df_stroked_angle %>%  filter(side == "left" & limb =="back")%>% select(-c(parameter, x_corr)) %>%  spread(parameter_short, y_corr, convert = F)


# Original Runway_Analysis.Rmd lines 1058-1058.
test_right_x_ba <- vertical_analysis_df_stroked_angle %>%   filter(side == "right" & limb == "back")%>%  select(-c(parameter, y_corr)) %>%  spread(parameter_short, x_corr, convert = F)


# Original Runway_Analysis.Rmd lines 1059-1059.
test_right_y_ba <- vertical_analysis_df_stroked_angle %>%   filter(side == "right" & limb == "back") %>% select(-c(parameter, x_corr)) %>%  spread(parameter_short, y_corr, convert = F)


# Original Runway_Analysis.Rmd lines 1063-1063.
left_angle_ba <- left_join(test_left_x_ba, test_left_y_ba,  by = c("full_id","mouse", "day",  "limb", "side", "time", "phase_numbers"))


# Original Runway_Analysis.Rmd lines 1064-1064.
right_angle_ba <- left_join(test_right_x_ba, test_right_y_ba, by = c("full_id", "mouse" ,"day",  "limb", "side", "time", "phase_numbers"))


# Original Runway_Analysis.Rmd lines 1088-1094.
left_angle_back_calc <- left_angle_ba %>%
  mutate(iliac_hip_ankle = (atan2((`back-ankle.y`-hip.y), (`back-ankle.x`-hip.x))- atan2((`iliac-crest.y`-hip.y), (`iliac-crest.x`-hip.x)))*180/pi) %>%
  mutate(hip_ankle_toe = (atan2((`back-toe.y`-`back-ankle.y`), (`back-toe.x`-`back-ankle.x`))- atan2((hip.y-`back-ankle.y`), (hip.x-`back-ankle.x`)))*180/pi) %>%
  select(-c(`back-ankle.x` , `back-ankle.y`, `back-toe.x`, `back-toe.y`,  hip.x, hip.y ,`iliac-crest.x`, `iliac-crest.y`)) %>%
  gather(Joints, Angle,  iliac_hip_ankle:hip_ankle_toe) %>%
  drop_na() %>%
  filter(Angle < 180) 


# Original Runway_Analysis.Rmd lines 1096-1102.
right_angle_back_calc <- right_angle_ba %>%
  mutate(iliac_hip_ankle = (atan2((`back-ankle.y`-hip.y), (`back-ankle.x`-hip.x))- atan2((`iliac-crest.y`-hip.y), (`iliac-crest.x`-hip.x)))*180/pi) %>%
  mutate(hip_ankle_toe = (atan2((`back-toe.y`-`back-ankle.y`), (`back-toe.x`-`back-ankle.x`))- atan2((hip.y-`back-ankle.y`), (hip.x-`back-ankle.x`)))*180/pi)%>%
  select(-c(`back-ankle.x` , `back-ankle.y`, `back-toe.x`, `back-toe.y`,  hip.x, hip.y ,`iliac-crest.x`, `iliac-crest.y`)) %>%
  gather(Joints, Angle,  iliac_hip_ankle:hip_ankle_toe) %>%
  drop_na() %>%
  filter(Angle < 180)


# Original Runway_Analysis.Rmd lines 1127-1132 — ALTERED as noted below.
summary_horizontal_angles <- bind_rows(left_angle_back_calc, right_angle_back_calc) %>%
  drop_na() %>%
  group_by(mouse, full_id, day, limb, side, Joints) %>%
  summarize(max_Angle= unname(quantile(Angle, 0.95)), min_Angle= unname(quantile(Angle, 0.1)), avg_Angle =mean(Angle)) %>%
  gather(Parameter, Value, max_Angle:avg_Angle) %>%
  mutate(Value = abs(Value))


# Original Runway_Analysis.Rmd lines 1134-1134.
summary_horizontal_angles$day_Num <- as.numeric(gsub("[^0-9.]", "",  summary_horizontal_angles$day))


# Original Runway_Analysis.Rmd lines 1171-1178 — ALTERED as noted below.
analysis_down <- Cycle_duration %>% 
  bind_rows(Stride_length) %>%
  bind_rows(Stance_Swing_time) %>% 
  rename(Measure = Parameter) %>%
  ungroup() %>% 
  select(full_id, day, mouse, Measure, Value) %>%
  mutate(ParameterGroup = "SynchrCycle_downPersp")


# Original Runway_Analysis.Rmd lines 1181-1186.
angle_down <- summary_angle_down %>%
  ungroup() %>%
  unite(Measure, joint, Parameter, sep = "__") %>%
  mutate(mouse = as.factor(sub(".*Mouse_", "" , summary_angle_down$full_id))) %>%
  select(full_id, day, mouse, Measure, Value) %>%
  mutate(ParameterGroup = "Angles_downPersp")


# Original Runway_Analysis.Rmd lines 1190-1195.
analysis_vertical <- summary_summary_vertical_analysis_df_3 %>%
  ungroup() %>%
  unite(Measure, parameter, Measure, sep = "__") %>%
  select(full_id, day, mouse, Measure, Value) %>%
  rename(Value = Value) %>%
  mutate(ParameterGroup = "VerticalHeight_Analysis_sidePersp")


# Original Runway_Analysis.Rmd lines 1198-1202.
analysis_pro_ret <- new_hz_steps %>%
  unite(Measure, side, limb, Measure, sep = "__") %>%
  ungroup() %>% 
  select(full_id, day, mouse, Measure, Value) %>%
  mutate(ParameterGroup = "ProtractionRetraction_sidePrsp")


# Original Runway_Analysis.Rmd lines 1206-1212.
analysis_duration <- duration_steps %>%
  rename(Value = seconds) %>%
  mutate(Measure = "seconds") %>%
  ungroup() %>%
  unite(Measure, side, limb, Measure, sep = "__") %>%
  select(full_id, day, mouse, Measure, Value) %>%
  mutate(ParameterGroup = "duration_step_sidePersp")


# Original Runway_Analysis.Rmd lines 1214-1220.
analysis_steps <- movement_per_step %>%
  rename(Value = x_corr_diff) %>%
  mutate(Measure = "movement_per_step") %>%
  ungroup() %>%
  unite(Measure, side, limb, Measure, sep = "__") %>%
  select(full_id ,day,  mouse, Measure, Value) %>%
  mutate(ParameterGroup = "moement_per_step_sidePersp")


# Original Runway_Analysis.Rmd lines 1223-1228.
angles_horizontal <- summary_horizontal_angles %>% 
  ungroup()%>%
  rename(Measure = Parameter)%>%
  unite(Measure, Measure, side, limb, Joints, sep = "__") %>%
   select(full_id ,day, mouse, Measure, Value) %>%
  mutate(ParameterGroup = "angles_horizontal_sidePersp")


# Original Runway_Analysis.Rmd lines 1230-1236.
all_raw_data <- analysis_down %>%
  bind_rows(angle_down) %>% 
  bind_rows(analysis_vertical) %>% 
  bind_rows(analysis_pro_ret) %>% 
  bind_rows(angles_horizontal) %>% 
  bind_rows(analysis_duration) %>%
  bind_rows(analysis_steps)


# Preserve the full 106-measure demo catalog and its exact CSV column schema.
# Height and pro/retraction Values are ABSOLUTE mm, not baseline changes.
catalog<-read.csv(text="Measure,ParameterGroup\nFLBR_RATIO,SynchrCycle_downPersp\nFRBL_RATIO,SynchrCycle_downPersp\navg_duration,SynchrCycle_downPersp\nduration_sd_diff,SynchrCycle_downPersp\navg_stride_length,SynchrCycle_downPersp\nstride_length_sd_diff,SynchrCycle_downPersp\navg_stance_time,SynchrCycle_downPersp\navg_swing_time,SynchrCycle_downPersp\nLB__max_Angle,Angles_downPersp\nLF__max_Angle,Angles_downPersp\nRB__max_Angle,Angles_downPersp\nRF__max_Angle,Angles_downPersp\nLB__min_Angle,Angles_downPersp\nLF__min_Angle,Angles_downPersp\nRB__min_Angle,Angles_downPersp\nRF__min_Angle,Angles_downPersp\nLB__avg_Angle,Angles_downPersp\nLF__avg_Angle,Angles_downPersp\nRB__avg_Angle,Angles_downPersp\nRF__avg_Angle,Angles_downPersp\nl-back-ankle__Average_Height,VerticalHeight_Analysis_sidePersp\nl-back-ankle__Movement,VerticalHeight_Analysis_sidePersp\nl-back-toe__Average_Height,VerticalHeight_Analysis_sidePersp\nl-back-toe__Movement,VerticalHeight_Analysis_sidePersp\nl-front-toe-tip__Average_Height,VerticalHeight_Analysis_sidePersp\nl-front-toe-tip__Movement,VerticalHeight_Analysis_sidePersp\nl-head__Average_Height,VerticalHeight_Analysis_sidePersp\nl-head__Movement,VerticalHeight_Analysis_sidePersp\nl-hip__Average_Height,VerticalHeight_Analysis_sidePersp\nl-hip__Movement,VerticalHeight_Analysis_sidePersp\nl-iliac-crest__Average_Height,VerticalHeight_Analysis_sidePersp\nl-iliac-crest__Movement,VerticalHeight_Analysis_sidePersp\nl-shoulder__Average_Height,VerticalHeight_Analysis_sidePersp\nl-shoulder__Movement,VerticalHeight_Analysis_sidePersp\nl-tail-base__Average_Height,VerticalHeight_Analysis_sidePersp\nl-tail-base__Movement,VerticalHeight_Analysis_sidePersp\nl-wrist__Average_Height,VerticalHeight_Analysis_sidePersp\nl-wrist__Movement,VerticalHeight_Analysis_sidePersp\nr-back-ankle__Average_Height,VerticalHeight_Analysis_sidePersp\nr-back-ankle__Movement,VerticalHeight_Analysis_sidePersp\nr-back-toe__Average_Height,VerticalHeight_Analysis_sidePersp\nr-back-toe__Movement,VerticalHeight_Analysis_sidePersp\nr-elbow__Average_Height,VerticalHeight_Analysis_sidePersp\nr-elbow__Movement,VerticalHeight_Analysis_sidePersp\nr-front-toe-tip__Average_Height,VerticalHeight_Analysis_sidePersp\nr-front-toe-tip__Movement,VerticalHeight_Analysis_sidePersp\nr-head__Average_Height,VerticalHeight_Analysis_sidePersp\nr-head__Movement,VerticalHeight_Analysis_sidePersp\nr-hip__Average_Height,VerticalHeight_Analysis_sidePersp\nr-hip__Movement,VerticalHeight_Analysis_sidePersp\nr-iliac-crest__Average_Height,VerticalHeight_Analysis_sidePersp\nr-iliac-crest__Movement,VerticalHeight_Analysis_sidePersp\nr-tail-base__Average_Height,VerticalHeight_Analysis_sidePersp\nr-tail-base__Movement,VerticalHeight_Analysis_sidePersp\nr-wrist__Average_Height,VerticalHeight_Analysis_sidePersp\nr-wrist__Movement,VerticalHeight_Analysis_sidePersp\nl-elbow__Average_Height,VerticalHeight_Analysis_sidePersp\nl-elbow__Movement,VerticalHeight_Analysis_sidePersp\nr-shoulder__Average_Height,VerticalHeight_Analysis_sidePersp\nr-shoulder__Movement,VerticalHeight_Analysis_sidePersp\nleft__back__retraction,ProtractionRetraction_sidePrsp\nleft__front__retraction,ProtractionRetraction_sidePrsp\nright__back__retraction,ProtractionRetraction_sidePrsp\nright__front__retraction,ProtractionRetraction_sidePrsp\nleft__back__protraction,ProtractionRetraction_sidePrsp\nleft__front__protraction,ProtractionRetraction_sidePrsp\nright__back__protraction,ProtractionRetraction_sidePrsp\nright__front__protraction,ProtractionRetraction_sidePrsp\nleft__back__average,ProtractionRetraction_sidePrsp\nleft__front__average,ProtractionRetraction_sidePrsp\nright__back__average,ProtractionRetraction_sidePrsp\nright__front__average,ProtractionRetraction_sidePrsp\nleft__back__median,ProtractionRetraction_sidePrsp\nleft__front__median,ProtractionRetraction_sidePrsp\nright__back__median,ProtractionRetraction_sidePrsp\nright__front__median,ProtractionRetraction_sidePrsp\nmax_Angle__left__back__hip_ankle_toe,angles_horizontal_sidePersp\nmax_Angle__left__back__iliac_hip_ankle,angles_horizontal_sidePersp\nmax_Angle__right__back__hip_ankle_toe,angles_horizontal_sidePersp\nmax_Angle__right__back__iliac_hip_ankle,angles_horizontal_sidePersp\nmax_Angle__left__front__ellbow_wrist_toetip,angles_horizontal_sidePersp\nmax_Angle__left__front__shoulder_ellbow_wrist,angles_horizontal_sidePersp\nmax_Angle__right__front__ellbow_wrist_toetip,angles_horizontal_sidePersp\nmax_Angle__right__front__shoulder_ellbow_wrist,angles_horizontal_sidePersp\nmin_Angle__left__back__hip_ankle_toe,angles_horizontal_sidePersp\nmin_Angle__left__back__iliac_hip_ankle,angles_horizontal_sidePersp\nmin_Angle__right__back__hip_ankle_toe,angles_horizontal_sidePersp\nmin_Angle__right__back__iliac_hip_ankle,angles_horizontal_sidePersp\nmin_Angle__left__front__ellbow_wrist_toetip,angles_horizontal_sidePersp\nmin_Angle__left__front__shoulder_ellbow_wrist,angles_horizontal_sidePersp\nmin_Angle__right__front__ellbow_wrist_toetip,angles_horizontal_sidePersp\nmin_Angle__right__front__shoulder_ellbow_wrist,angles_horizontal_sidePersp\navg_Angle__left__back__hip_ankle_toe,angles_horizontal_sidePersp\navg_Angle__left__back__iliac_hip_ankle,angles_horizontal_sidePersp\navg_Angle__right__back__hip_ankle_toe,angles_horizontal_sidePersp\navg_Angle__right__back__iliac_hip_ankle,angles_horizontal_sidePersp\navg_Angle__left__front__ellbow_wrist_toetip,angles_horizontal_sidePersp\navg_Angle__left__front__shoulder_ellbow_wrist,angles_horizontal_sidePersp\navg_Angle__right__front__ellbow_wrist_toetip,angles_horizontal_sidePersp\navg_Angle__right__front__shoulder_ellbow_wrist,angles_horizontal_sidePersp\nleft__back__seconds,duration_step_sidePersp\nleft__front__seconds,duration_step_sidePersp\nright__back__seconds,duration_step_sidePersp\nright__front__seconds,duration_step_sidePersp\nleft__back__movement_per_step,moement_per_step_sidePersp\nright__back__movement_per_step,moement_per_step_sidePersp",stringsAsFactors=FALSE)
native_raw_data<-as.data.frame(all_raw_data)
stopifnot(!anyDuplicated(native_raw_data$Measure))
positions<-match(catalog$Measure,native_raw_data$Measure)
all_raw_data<-data.frame(full_id=FULL_ID,day=DAY,mouse=MOUSE,Measure=catalog$Measure,
  Value=native_raw_data$Value[positions],ParameterGroup=catalog$ParameterGroup,stringsAsFactors=FALSE)


# FULL-CATALOG EXPORT: retain all original rows, but do not calculate forelimbs.
# Both forelimb-specific entries and fore/hind coordination ratios stay NA.
forelimb_catalog_rows<-grepl('front|wrist|elbow|ellbow|shoulder|^LF__|^RF__|^FLBR_RATIO$|^FRBL_RATIO$',all_raw_data$Measure)
all_raw_data$Value[forelimb_catalog_rows]<-NA_real_
stopifnot(nrow(all_raw_data)==106L,sum(forelimb_catalog_rows)==46L)


# Original Runway_Analysis.Rmd lines 1241-1243.
all_sum_data <- all_raw_data %>%
  group_by(day, Measure, ParameterGroup) %>%
  summarize(Mean = mean(Value), median = median(Value), sd = sd(Value), sem = sd(Value) / sqrt(length(Value)) )

# 7. Original-format CSV exports and per-stride RustLab1 values ----------------
write.csv(all_raw_data,file.path(output_dir,'all_raw_data.csv'),na='NA')
write.csv(all_sum_data,file.path(output_dir,'all_summarized_data.csv'),na='NA')
per_stride<-list()
for(i in seq_len(nrow(canonical))){
  w<-canonical[i,];id<-w$cycle_id
  view<-Speed_down_cycle[Speed_down_cycle$phase_numbers==id & Speed_down_cycle$parameter==w$parameter,]
  local<-new.env(parent=globalenv());local$Speed_down_cycle<-view
  eval(expr_Stride_length,envir=local)
  length_cm<-local$Stride_length$Value[local$Stride_length$Parameter=='avg_stride_length'][1L]
  vd<-vertical_df_steps[vertical_df_steps$phase_numbers==id & vertical_df_steps$side==w$side & vertical_df_steps$limb==w$limb,]
  vv<-eval_steps(vd,pipe_parts(expr_summary_vertical_analysis_df_stroked[[3]])[2:4])
  hh<-eval_steps(vd,pipe_parts(expr_horizontal_df[[3]])[2:4])
  markers<-unique(vd$parameter)
  for(marker in markers){
    vr<-vv[vv$parameter==marker,];hr<-hh[hh$parameter==marker,]
    per_stride[[length(per_stride)+1L]]<-data.frame(reference_paw=w$parameter,side=w$side,limb=w$limb,
      stride_or_phase_id=id,window_type='assembler_GMM_complete_cycle',start_frame=w$start_frame,
      end_frame_inclusive=w$end_frame_inclusive,R_duration_seconds=w$cycle_duration_seconds,
      R_stride_length_cm=length_cm,marker=marker,R_vertical_excursion_px=vr$y_max_norm[[1]],
      R_mean_relative_height_px=vr$mean_norm[[1]],R_horizontal_excursion_px=hr$Movement[[1]])
  }
}
per_stride<-bind_rows(per_stride)
write.csv(per_stride,file.path(output_dir,'Per_stride_parameters.csv'),row.names=FALSE,na='NA')
write.csv(phase_labels,file.path(output_dir,'Stride_detection.csv'),row.names=FALSE,na='NA')

# Save diagnostics outside the result folder. They permit independent checking
# of source-coordinate retention, smoothing, R intermediate values and labels.
tables<-list(long_data_clean2=long_data_clean2,vertical_df_steps=vertical_df_steps,
  summary_vertical_analysis_df_stroked=summary_vertical_analysis_df_stroked,
  summary_summary_vertical_analysis_df_2=summary_summary_vertical_analysis_df_2,
  summary_summary_vertical_analysis_df_3=summary_summary_vertical_analysis_df_3,
  horizontal_df_steps=horizontal_df_steps,new_hz_steps=new_hz_steps,
  summary_horizontal_angles=summary_horizontal_angles,all_raw_data=all_raw_data,
  all_sum_data=all_sum_data,per_stride=per_stride,canonical=canonical)
for(name in names(tables))write.csv(as.data.frame(tables[[name]]),
  file.path(diagnostics_dir,paste0(name,'.csv')),row.names=FALSE,na='NA')
saveRDS(tables,file.path(diagnostics_dir,'adapted_R_workspace.rds'))
settings<-list(analysis='adapted_RustLab1_R_with_existing_Speed_GMM_hindlimb_only',scope='hindlimb only',
  parameter_confidence_filter='disabled; retain all finite coordinates',camera_ROI_filter='disabled',
  vertical_5_to_30_px_rejection='disabled',protraction_minus100_to_60_px_rejection='disabled',
  baseline_subtraction='disabled; absolute heights and signed distances in mm',
  butterworth=list(enabled=BUTTERWORTH_ENABLED,order=5,cutoff_hz=BUTTERWORTH_CUTOFF_HZ,passes='forward/backward',
    phase='zero phase',pad_type='odd reflection',pad_length=18,fps=FPS),
  gap_repair=list(maximum_frames=MAX_INTERNAL_GAP,inside_same_complete_GMM_cycle=TRUE,extrapolate=FALSE),
  calibration=list(pixels_per_cm=PIXELS_PER_CM,stride_pixels_per_cm=STRIDE_PIXELS_PER_CM,
    arbitrary=as.logical(setting('reference_scale',TRUE))),
  existing_GMM_timing_likelihood_cutoff=as.numeric(setting('timing_likelihood_threshold',0.5)),complete_cycles=nrow(canonical),
  numeric_catalog_values=sum(is.finite(all_raw_data$Value)),missing_catalog_values=sum(is.na(all_raw_data$Value)))
jsonlite::write_json(settings,file.path(diagnostics_dir,'run_settings.json'),pretty=TRUE,auto_unbox=TRUE)

# 8. Stickplots: existing assembler generation algorithm ---------------------
# The renderer receives exactly the R-smoothed native coordinates used above.
# No ALMA gait-parameter calculations are called. Only the existing stickplot
# preparation/renderer is used. Original GMM phase colors and starts are retained.
if(!'--no-stickplots' %in% argv){
  python_code<-r"---(
from pathlib import Path
import os
import sys
import numpy as np
import pandas as pd
diagnostics,out,repo,phase_path=map(Path,sys.argv[1:])
os.environ.setdefault('MPLCONFIGDIR',str(diagnostics/'matplotlib_cache'))
import matplotlib
matplotlib.use('Agg')
from matplotlib.figure import Figure
sys.path.insert(0,str(repo/'src'))
from dlc_gait_assembly.runway.manual.gait_analysis.business.alma.alma_analysis_settings import ALMA_BODYPARTS
from dlc_gait_assembly.runway.manual.gait_analysis.business.alma.alma_continuous_sequences import prepare_full_recording_stickplot
from dlc_gait_assembly.runway.manual.gait_analysis.infrastructure.figures.gait_stickplot_renderer import render_prepared_stickplot
cycles=pd.read_csv(diagnostics/'canonical.csv')
phase=pd.read_csv(phase_path)
original_save=Figure.savefig
def save_png(self,filename,*args,**kwargs):
    kwargs['format']='png'
    kwargs['dpi']=180
    return original_save(self,filename,*args,**kwargs)
Figure.savefig=save_png
try:
    for side in ('left','right'):
        raw=pd.read_csv(diagnostics/f'native_{side}.csv')
        mapping={'toe':'toe' if side=='left' else 'back_toe','mtp':'MTP','ankle':'ankle',
                 'knee':'knee','hip':'hip','iliac crest':'iliac_crest'}
        coords=pd.DataFrame({f'{dest} {axis}':raw[f'{source} {axis}']
                             for dest,source in mapping.items() for axis in ('x','y')})
        own=phase[phase.parameter.eq('d-back-'+side)].sort_values('source_frame')
        stance=own.phase_names.eq('stance').to_numpy()
        coords.attrs.update(view_label=side.title(),stride_method='Speed GMM | adapted RustLab1 | ALMA Butterworth 5th order, 6 Hz',
            timing_source='Unchanged side-toe Speed GMM cycles; all finite parameter coordinates',
            detection_diagnostics={'trusted':own.trusted.to_numpy(bool)})
        accepted=cycles[cycles.parameter.eq('d-back-'+side)]
        parameters=pd.DataFrame({'stride_start (frame)':accepted.start_frame,
                                 'stride_end (frame)':accepted.end_frame_inclusive,
                                 'cycle duration (s)':accepted.cycle_duration_seconds})
        prepared=prepare_full_recording_stickplot(parameters,coords,ALMA_BODYPARTS,stance)
        assert prepared is not None
        render_prepared_stickplot(prepared,out/f'Stickplot_{side}.png')
finally:
    Figure.savefig=original_save
)---"
  python_script<-file.path(diagnostics_dir,'render_current_stickplots.py')
  writeLines(python_code,python_script)
  status<-system2(python,vapply(c(python_script,diagnostics_dir,output_dir,repo_root,file.path(output_dir,'Stride_detection.csv')),shQuote,character(1)))
  stopifnot(status==0L)
}
cat('Adapted RustLab1 R run:',sum(is.finite(all_raw_data$Value)),'numeric catalog values;',
    sum(is.na(all_raw_data$Value)),'missing;',nrow(per_stride),'per-stride marker rows.\n')
