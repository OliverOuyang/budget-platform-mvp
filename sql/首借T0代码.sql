/*******************************************************************************
 * Query Set: First Loan T0 Business Metrics
 * File: 首借T0代码.sql
 * Description: Comprehensive first loan T0 conversion funnel metrics
 *              - Query 1: Monthly aggregation by channel
 *              - Query 2: Daily detailed metrics with asset breakdown
 * Author: Data Analysis Team
 * Last Updated: 2026-03-31
 ******************************************************************************/


/*******************************************************************************
 * QUERY 1: Monthly Channel Core Metrics
 *
 * Purpose: Calculate monthly T0 and first-login M0 transaction metrics by channel
 * Granularity: month + channel_category
 * Data Range: All historical data (no WHERE filter)
 * Update Frequency: Daily incremental
 * Business Owner: Marketing & Acquisition Team
 ******************************************************************************/

WITH base_data AS (
    -- First loan detail table with T0 and M0 transaction amounts
    SELECT
        uid,
        date_key,
        login_t0_btch_first_loan_success_principal_24h,
        login_m0_btch_first_loan_success_principal_24h
    FROM dwt.dwt_marketing_date_user_index_df_login
    WHERE ds = '${bizdate}'
),
user_info AS (
    -- User attribution and channel information
    SELECT
        uid,
        marketing_channel_group_name,
        first_credit_law_type                                   -- First credit type: '初审' or others
    FROM dwt.dwt_marketing_attribution_user_comprehensive_info_df
    WHERE ds = '${bizdate}'
),
channel_mapping AS (
    -- Standardized channel category mapping
    SELECT
        a.uid,
        a.date_key,
        a.login_t0_btch_first_loan_success_principal_24h,
        a.login_m0_btch_first_loan_success_principal_24h,
        b.first_credit_law_type,
        -- Channel category aggregation (aligned with daily query)
        CASE
            WHEN b.marketing_channel_group_name = '精准营销' THEN '精准营销'
            WHEN b.marketing_channel_group_name IN ('抖音', '抖音二组', '抖音中组', '抖音品专') THEN '抖音'
            WHEN b.marketing_channel_group_name IN ('微信小程序', '腾讯二组', '腾讯中组', '腾讯h5') THEN '腾讯'
            WHEN b.marketing_channel_group_name IN ('百度信息流', '快手', '百度sem', '百度sem品专', '百度sem开屏', '广点通', 'B站', '粉丝通', '穿山甲') THEN '其他信息流'
            WHEN b.marketing_channel_group_name IN ('私域获客', '行业渠道') THEN '其他CPA渠道'
            WHEN b.marketing_channel_group_name = 'API' THEN 'API'
            WHEN b.marketing_channel_group_name IN ('华为付费商店', 'OV+小米付费商店', '付费应用商店', 'VIVO信息流', '华为信息流', 'OPPO信息流', '荣耀付费商店', 'asa', '苹果付费商店') THEN '付费商店'
            WHEN b.marketing_channel_group_name IN ('自然量', '公众号') THEN '免费渠道'
            WHEN b.marketing_channel_group_name = 'MGM' THEN 'MGM'
            ELSE '其他'
        END AS channel_category
    FROM base_data a
    LEFT JOIN user_info b
        ON a.uid = b.uid
)

-- Final aggregation by month and channel
SELECT
    -- ==================== Dimension: Time ====================
    SUBSTR(date_key, 1, 7) AS 月份,                             -- Month (YYYY-MM format)

    -- ==================== Dimension: Channel ====================
    channel_category AS 渠道类别,                                -- Standardized channel category

    -- ==================== Metric: T0 Transaction ====================
    SUM(
        IF(first_credit_law_type = '初审',
           login_t0_btch_first_loan_success_principal_24h,
           0)
    ) AS t0_loa_amt_24h,                                        -- T0 day first loan 24h disbursement amount

    -- ==================== Metric: First Login M0 Transaction ====================
    SUM(
        IF(first_credit_law_type = '初审',
           login_m0_btch_first_loan_success_principal_24h,
           0)
    ) AS sd_m0_loa_amt_24h,                                     -- First login M0 24h disbursement amount

    -- ==================== Metric: Ratio ====================
    -- Ratio of first-login M0 transaction to T0 transaction
    CASE
        WHEN SUM(IF(first_credit_law_type = '初审', login_t0_btch_first_loan_success_principal_24h, 0)) > 0
        THEN SUM(IF(first_credit_law_type = '初审', login_m0_btch_first_loan_success_principal_24h, 0)) * 1.0
             / SUM(IF(first_credit_law_type = '初审', login_t0_btch_first_loan_success_principal_24h, 0))
        ELSE NULL
    END AS 当月首登M0_T0_24h_交易比值                             -- Monthly first-login M0/T0 24h transaction ratio

FROM channel_mapping

GROUP BY
    SUBSTR(date_key, 1, 7),
    channel_category
;


/*******************************************************************************
 * QUERY 2: Daily First Loan T0 Detailed Business Metrics
 *
 * Purpose: Daily conversion funnel metrics with platform, channel, and asset breakdown
 * Granularity: date + platform + channel_category + asset_category + a_score + is_age_refuse
 * Data Range: Configurable via WHERE clause (default: from 2026-03-01)
 * Update Frequency: Daily
 * Business Owner: Risk & Product Team
 ******************************************************************************/

WITH base_data_daily AS (
    -- User daily behavior metrics from login dimension table
    SELECT
        uid,
        date_key,
        -- Login and application metrics
        first_login_user_count,
        login_t0_apply_finish_user_count,
        login_t0_btch_first_credit_user_count,
        login_t0_btch_loan_apply_user_count,
        login_t0_btch_loan_risk_pass_user_count,
        login_t0_btch_loan_success_user_count,
        login_t30_apply_finish_user_count,
        login_t30_btch_first_credit_user_count,
        login_t30_btch_loan_apply_user_count,
        login_t30_btch_loan_risk_pass_user_count,
        login_t30_btch_loan_success_user_count,
        -- Credit limit and transaction amounts
        login_t0_btch_first_risk_credit_limit,
        login_t0_btch_loan_success_principal,
        login_t0_btch_loan_apply_amount,
        login_t0_btch_first_loan_success_principal_24h,
        login_t3_btch_first_loan_success_principal_24h,
        login_t7_btch_first_loan_success_principal_24h,
        login_t30_btch_loan_success_principal,
        login_t30_btch_first_loan_success_principal_24h,
        -- First login M0 metrics
        login_m0_apply_finish_user_count,
        login_m0_btch_first_credit_user_count,
        login_m0_btch_first_loan_apply_user_count,
        login_m0_btch_first_loan_risk_pass_user_count,
        login_m0_btch_first_loan_success_user_count,
        login_m0_btch_first_risk_credit_limit,
        login_m0_btch_first_loan_success_principal,
        login_m0_btch_first_loan_success_principal_24h
    FROM dwt.dwt_marketing_date_user_index_df_login
    WHERE ds = '${bizdate}'
),
user_comprehensive_info AS (
    -- User attribution and risk classification
    SELECT
        uid,
        first_login_platform_api_app_mp,                        -- First login platform: APP/Mini Program/H5
        marketing_channel_group_name,                           -- Marketing channel group
        initial_risk_model_merge_a_score_group,                 -- A-score group (1-8)
        is_age_refuse,                                          -- Age rejection flag (1=rejected, 0=not rejected)
        first_credit_law_type,                                  -- Credit type: '初审' (first audit) or others
        first_login_time_app_mp,                                -- First login timestamp
        first_loan_date_btch                                    -- First loan date
    FROM dwt.dwt_marketing_attribution_user_comprehensive_info_df
    WHERE ds = '${bizdate}'
),
enriched_data AS (
    -- Join user behavior with attribution info and derive additional dimensions
    SELECT
        a.date_key,
        b.first_login_platform_api_app_mp AS platform,
        b.initial_risk_model_merge_a_score_group AS a_scr,
        b.is_age_refuse,
        b.first_credit_law_type,

        -- ==================== Derived Dimension: Channel Category ====================
        CASE
            WHEN b.marketing_channel_group_name = '精准营销' THEN '精准营销'
            WHEN b.marketing_channel_group_name IN ('抖音', '抖音二组', '抖音中组', '抖音品专') THEN '抖音'
            WHEN b.marketing_channel_group_name IN ('微信小程序', '腾讯二组', '腾讯中组', '腾讯h5') THEN '腾讯'
            WHEN b.marketing_channel_group_name IN ('百度信息流', '快手', '百度sem', '百度sem品专', '百度sem开屏', '广点通', 'B站', '粉丝通', '穿山甲') THEN '其他信息流'
            WHEN b.marketing_channel_group_name IN ('私域获客', '行业渠道') THEN '其他CPA渠道'
            WHEN b.marketing_channel_group_name = 'API' THEN 'API'
            WHEN b.marketing_channel_group_name IN ('华为付费商店', 'OV+小米付费商店', '付费应用商店', 'VIVO信息流', '华为信息流', 'OPPO信息流', '荣耀付费商店', 'asa', '苹果付费商店') THEN '付费商店'
            WHEN b.marketing_channel_group_name IN ('自然量', '公众号') THEN '免费渠道'
            WHEN b.marketing_channel_group_name = 'MGM' THEN 'MGM'
            ELSE '其他'
        END AS 渠道类别,

        -- ==================== Derived Dimension: Asset Category ====================
        -- Asset classification based on A-score groups
        CASE
            WHEN b.initial_risk_model_merge_a_score_group IN (1, 2, 3) THEN '安全资产'        -- Safe assets
            WHEN b.initial_risk_model_merge_a_score_group IN (4, 5, 6, 7) THEN '非安全资产'  -- Non-safe assets
            WHEN b.initial_risk_model_merge_a_score_group = 8 THEN '下探资产'                -- Downgrade assets
            ELSE NULL
        END AS 资产类别,

        -- ==================== Derived Flag: T0 Trader ====================
        -- Identify users who traded on the same day as first login
        CASE
            WHEN SUBSTR(b.first_login_time_app_mp, 1, 10) = SUBSTR(b.first_loan_date_btch, 1, 10) THEN 1
            ELSE 0
        END AS is_t0_trader,

        -- All metric fields from base table
        a.first_login_user_count,
        a.login_t0_apply_finish_user_count,
        a.login_t0_btch_first_credit_user_count,
        a.login_t0_btch_loan_apply_user_count,
        a.login_t0_btch_loan_risk_pass_user_count,
        a.login_t0_btch_loan_success_user_count,
        a.login_t30_apply_finish_user_count,
        a.login_t30_btch_first_credit_user_count,
        a.login_t30_btch_loan_apply_user_count,
        a.login_t30_btch_loan_risk_pass_user_count,
        a.login_t30_btch_loan_success_user_count,
        a.login_t0_btch_first_risk_credit_limit,
        a.login_t0_btch_loan_success_principal,
        a.login_t0_btch_loan_apply_amount,
        a.login_t0_btch_first_loan_success_principal_24h,
        a.login_t3_btch_first_loan_success_principal_24h,
        a.login_t7_btch_first_loan_success_principal_24h,
        a.login_t30_btch_loan_success_principal,
        a.login_t30_btch_first_loan_success_principal_24h,
        a.login_m0_apply_finish_user_count,
        a.login_m0_btch_first_credit_user_count,
        a.login_m0_btch_first_loan_apply_user_count,
        a.login_m0_btch_first_loan_risk_pass_user_count,
        a.login_m0_btch_first_loan_success_user_count,
        a.login_m0_btch_first_risk_credit_limit,
        a.login_m0_btch_first_loan_success_principal,
        a.login_m0_btch_first_loan_success_principal_24h

    FROM base_data_daily a
    LEFT JOIN user_comprehensive_info b
        ON a.uid = b.uid

    WHERE
        -- Configurable date range filter
        TO_DATE(a.date_key) >= '2026-03-01'
        -- Optional additional filters (uncomment as needed):
        -- AND b.marketing_channel_group_name <> 'API'           -- Exclude API channel
        -- AND b.cust_type = '渠道'                               -- Channel customers only
        -- AND b.first_credit_law_type = '初审'                  -- First audit only
)

-- Final aggregation with all dimensions and metrics
SELECT
    -- ==================== Dimension Fields ====================
    date_key,                                                   -- Date (YYYY-MM-DD)
    platform,                                                   -- First login platform
    渠道类别,                                                    -- Channel category
    资产类别,                                                    -- Asset category
    a_scr,                                                      -- A-score group (1-8)
    is_age_refuse,                                              -- Age rejection flag

    -- ==================== User Count Metrics: T0 Conversion Funnel ====================
    SUM(first_login_user_count) AS log_num,                                                 -- First login users
    SUM(login_t0_apply_finish_user_count) AS t0_ato_num,                                    -- T0 application complete users
    SUM(IF(first_credit_law_type = '初审', login_t0_btch_first_credit_user_count, 0)) AS t0_adt_num,     -- T0 credit granted users
    SUM(IF(first_credit_law_type = '初审', login_t0_btch_loan_apply_user_count, 0)) AS t0_apl_num,       -- T0 loan apply users
    SUM(IF(first_credit_law_type = '初审', login_t0_btch_loan_risk_pass_user_count, 0)) AS t0_rsk_num,   -- T0 risk pass users
    SUM(IF(first_credit_law_type = '初审', login_t0_btch_loan_success_user_count, 0)) AS t0_loa_num,     -- T0 loan success users

    -- ==================== User Count Metrics: T30 Conversion Funnel ====================
    SUM(login_t30_apply_finish_user_count) AS t30_ato_num,                                  -- T30 application complete users
    SUM(IF(first_credit_law_type = '初审', login_t30_btch_first_credit_user_count, 0)) AS t30_adt_num,   -- T30 credit granted users
    SUM(IF(first_credit_law_type = '初审', login_t30_btch_loan_apply_user_count, 0)) AS t30_apl_num,     -- T30 loan apply users
    SUM(IF(first_credit_law_type = '初审', login_t30_btch_loan_risk_pass_user_count, 0)) AS t30_rsk_num, -- T30 risk pass users
    SUM(IF(first_credit_law_type = '初审', login_t30_btch_loan_success_user_count, 0)) AS t30_loa_num,   -- T30 loan success users

    -- ==================== Amount Metrics: Credit Limit ====================
    SUM(IF(first_credit_law_type = '初审', login_t0_btch_first_risk_credit_limit, 0)) AS t0_adt_amt,     -- T0 initial credit limit
    SUM(
        IF(first_credit_law_type = '初审' AND is_t0_trader = 1,
           login_t0_btch_first_risk_credit_limit,
           0)
    ) AS t0_adt_amt_jyh,                                                                     -- T0 trader initial credit limit

    -- ==================== Amount Metrics: T0 Transaction ====================
    SUM(IF(first_credit_law_type = '初审', login_t0_btch_loan_success_principal, 0)) AS t0_loa_amt,      -- T0 total transaction amount
    SUM(IF(first_credit_law_type = '初审', login_t0_btch_loan_apply_amount, 0)) AS t0_aply_amt,          -- T0 apply amount
    SUM(IF(first_credit_law_type = '初审', login_t0_btch_first_loan_success_principal_24h, 0)) AS t0_loa_amt_24h,   -- T0 24h transaction amount
    SUM(IF(first_credit_law_type = '初审', login_t3_btch_first_loan_success_principal_24h, 0)) AS t3_loa_amt_24h,   -- T3 24h transaction amount
    SUM(IF(first_credit_law_type = '初审', login_t7_btch_first_loan_success_principal_24h, 0)) AS t7_loa_amt_24h,   -- T7 24h transaction amount

    -- ==================== Amount Metrics: T30 Transaction ====================
    SUM(IF(first_credit_law_type = '初审', login_t30_btch_loan_success_principal, 0)) AS t30_loa_amt,               -- T30 total transaction amount
    SUM(IF(first_credit_law_type = '初审', login_t30_btch_first_loan_success_principal_24h, 0)) AS t30_loa_amt_24h, -- T30 24h transaction amount

    -- ==================== First Login M0 Metrics ====================
    SUM(login_m0_apply_finish_user_count) AS sd_m0_ato_num,                                                -- First login M0 application complete users
    SUM(IF(first_credit_law_type = '初审', login_m0_btch_first_credit_user_count, 0)) AS sd_m0_adt_num,           -- First login M0 credit granted users
    SUM(IF(first_credit_law_type = '初审', login_m0_btch_first_loan_apply_user_count, 0)) AS sd_m0_apl_num,       -- First login M0 loan apply users
    SUM(IF(first_credit_law_type = '初审', login_m0_btch_first_loan_risk_pass_user_count, 0)) AS sd_m0_rsk_num,   -- First login M0 risk pass users
    SUM(IF(first_credit_law_type = '初审', login_m0_btch_first_loan_success_user_count, 0)) AS sd_m0_loa_num,     -- First login M0 loan success users
    SUM(IF(first_credit_law_type = '初审', login_m0_btch_first_risk_credit_limit, 0)) AS sd_m0_adt_amt,           -- First login M0 initial credit limit
    SUM(IF(first_credit_law_type = '初审', login_m0_btch_first_loan_success_principal, 0)) AS sd_m0_loa_amt,      -- First login M0 transaction amount
    SUM(IF(first_credit_law_type = '初审', login_m0_btch_first_loan_success_principal_24h, 0)) AS sd_m0_loa_amt_24h -- First login M0 24h transaction amount

FROM enriched_data

GROUP BY
    date_key,
    platform,
    渠道类别,
    资产类别,
    a_scr,
    is_age_refuse
;


/*******************************************************************************
 * Business Glossary and Technical Notes
 *
 * === Time Window Definitions ===
 * - T0:  Same day as first login (date_key = first_login_date)
 * - T3:  Within 3 days of first login
 * - T7:  Within 7 days of first login
 * - T30: Within 30 days of first login
 * - M0:  Same calendar month as first login
 * - 24h: Within 24 hours of the event (regardless of calendar day boundary)
 *
 * === Conversion Funnel Stages ===
 * 1. log (First Login):     User first opens the app/mini-program
 * 2. ato (Apply To):        User completes application form
 * 3. adt (Audit):           User receives credit approval
 * 4. apl (Apply):           User initiates loan request
 * 5. rsk (Risk Pass):       Loan request passes risk control
 * 6. loa (Loan Success):    Loan is successfully disbursed
 *
 * === Asset Categories (based on A-score) ===
 * - 安全资产 (Safe Assets):        A-score groups 1, 2, 3
 * - 非安全资产 (Non-Safe Assets):  A-score groups 4, 5, 6, 7
 * - 下探资产 (Downgrade Assets):   A-score group 8
 *
 * === Channel Grouping Logic ===
 * Channels are grouped into 9 major categories:
 * 1. 精准营销 (Precision Marketing)
 * 2. 抖音 (Douyin/TikTok)
 * 3. 腾讯 (Tencent/WeChat)
 * 4. 其他信息流 (Other News Feeds): Baidu, Kuaishou, B站, etc.
 * 5. 其他CPA渠道 (Other CPA Channels): Private domain, industry channels
 * 6. API
 * 7. 付费商店 (Paid App Stores): Huawei, OPPO, VIVO, Apple ASA, etc.
 * 8. 免费渠道 (Free Channels): Organic traffic, WeChat official account
 * 9. MGM (Member Get Member)
 * 10. 其他 (Others): Catch-all for unmapped channels
 *
 * === Important Business Rules ===
 * - first_credit_law_type = '初审': Only counts first-time credit users
 * - is_age_refuse = 1: User rejected due to age restrictions
 * - T0 trader (t0_adt_amt_jyh): Users whose first_login_date = first_loan_date
 *
 * === Data Sources ===
 * - dwt.dwt_marketing_date_user_index_df_login: Daily user behavior metrics
 * - dwt.dwt_marketing_attribution_user_comprehensive_info_df: User attribution and risk profile
 * - Both tables use ds = '${bizdate}' partition
 *
 * === Technical Notes ===
 * - Query uses LEFT JOIN to preserve all login records even if user info is missing
 * - CASE statements are extracted to CTE level to avoid duplication in GROUP BY
 * - All amount metrics filtered by first_credit_law_type = '初审' to ensure first-time loans only
 * - Date range is configurable via WHERE clause in enriched_data CTE
 ******************************************************************************/
