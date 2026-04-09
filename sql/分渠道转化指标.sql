/*******************************************************************************
 * 查询名称: 分渠道转化指标分析
 * 功能说明: 统计不同渠道、平台、资产类别的用户转化漏斗指标
 * 数据粒度: 日期 + 平台 + 渠道类别 + 资产类别 + A评分组 + 年龄拒绝标识
 * 数据范围: 2026-03-01 起(可调整)
 * 更新频率: 每日
 ******************************************************************************/

SELECT
    -- ==================== 维度字段 ====================
    a.date_key,                                             -- 日期
    b.first_login_platform_api_app_mp AS platform,         -- 首次登录平台

    -- 渠道类别分类(合并细分渠道为大类)
    CASE
        WHEN b.marketing_channel_group_name = '精准营销' THEN '精准营销'
        WHEN b.marketing_channel_group_name IN ('抖音', '抖音二组', '抖音中组', '抖音品专') THEN '抖音'
        WHEN b.marketing_channel_group_name IN ('微信小程序', '腾讯二组', '腾讯中组', '腾讯h5') THEN '腾讯'
        WHEN b.marketing_channel_group_name IN ('百度信息流', '快手', '百度sem', '百度sem品专', '百度sem开屏', '广点通', 'B站', '粉丝通', '穿山甲') THEN '其他信息流'
        WHEN b.marketing_channel_group_name IN ('私域获客', '行业渠道') THEN '其他CPA渠道'
        WHEN b.marketing_channel_group_name = 'API' THEN 'API'
        WHEN b.marketing_channel_group_name IN ('华为付费商店', 'OV+小米付费商店', '付费应用商店', 'VIVO信息流', '华为信息流', 'OPPO信息流', '荣耀付费商店', 'asa', '苹果付费商店') THEN '付费商店'
        WHEN b.marketing_channel_group_name IN ('自然量', '公众号') THEN '免费渠道'
        WHEN b.marketing_channel_group_name IN ('MGM') THEN 'MGM'
        ELSE '其他'
    END AS 渠道类别,

    -- 资产类别分类(基于A评分分组)
    CASE
        WHEN b.initial_risk_model_merge_a_score_group IN (1, 2, 3) THEN '安全资产'
        WHEN b.initial_risk_model_merge_a_score_group IN (4, 5, 6, 7) THEN '非安全资产'
        WHEN b.initial_risk_model_merge_a_score_group = 8 THEN '下探资产'
        ELSE NULL
    END AS 资产类别,

    b.initial_risk_model_merge_a_score_group AS a_scr,     -- A评分分组
    b.is_age_refuse,                                        -- 年龄拒绝标识

    -- ==================== T0转化指标(首次登录当天) ====================
    SUM(a.first_login_user_count) AS log_num,                                                      -- 首次登录用户数
    SUM(a.login_t0_apply_finish_user_count) AS t0_ato_num,                                         -- T0申完户数
    SUM(IF(b.first_credit_law_type = '初审', a.login_t0_btch_first_credit_user_count, 0)) AS t0_adt_num,      -- T0授信户数(初审)
    SUM(IF(b.first_credit_law_type = '初审', a.login_t0_btch_loan_apply_user_count, 0)) AS t0_apl_num,        -- T0发起户数(初审)
    SUM(IF(b.first_credit_law_type = '初审', a.login_t0_btch_loan_risk_pass_user_count, 0)) AS t0_rsk_num,    -- T0风险通过户数(初审)
    SUM(IF(b.first_credit_law_type = '初审', a.login_t0_btch_loan_success_user_count, 0)) AS t0_loa_num,      -- T0借款户数(初审)

    -- ==================== T30转化指标(首次登录后30天) ====================
    SUM(a.login_t30_apply_finish_user_count) AS t30_ato_num,                                       -- T30申完户数
    SUM(IF(b.first_credit_law_type = '初审', a.login_t30_btch_first_credit_user_count, 0)) AS t30_adt_num,    -- T30授信户数(初审)
    SUM(IF(b.first_credit_law_type = '初审', a.login_t30_btch_loan_apply_user_count, 0)) AS t30_apl_num,      -- T30发起户数(初审)
    SUM(IF(b.first_credit_law_type = '初审', a.login_t30_btch_loan_risk_pass_user_count, 0)) AS t30_rsk_num,  -- T30风险通过户数(初审)
    SUM(IF(b.first_credit_law_type = '初审', a.login_t30_btch_loan_success_user_count, 0)) AS t30_loa_num,    -- T30借款户数(初审)

    -- ==================== T0金额指标 ====================
    SUM(IF(b.first_credit_law_type = '初审', a.login_t0_btch_first_risk_credit_limit, 0)) AS t0_adt_amt,      -- T0初始授信额度
    SUM(IF(b.first_credit_law_type = '初审' AND SUBSTR(b.first_login_time_app_mp, 1, 10) = SUBSTR(b.first_loan_date_btch, 1, 10),
        a.login_t0_btch_first_risk_credit_limit, 0)) AS t0_adt_amt_jyh,                                        -- T0交易户初始授信额度
    SUM(IF(b.first_credit_law_type = '初审', a.login_t0_btch_loan_success_principal, 0)) AS t0_loa_amt,       -- T0交易额
    SUM(IF(b.first_credit_law_type = '初审', a.login_t0_btch_loan_apply_amount, 0)) AS t0_aply_amt,           -- T0发起金额
    SUM(IF(b.first_credit_law_type = '初审', a.login_t0_btch_first_loan_success_principal_24h, 0)) AS t0_loa_amt_24h,  -- T0交易额(24小时内)

    -- ==================== T3/T7/T30金额指标(24小时内交易) ====================
    SUM(IF(b.first_credit_law_type = '初审', a.login_t3_btch_first_loan_success_principal_24h, 0)) AS t3_loa_amt_24h,  -- T3交易额(24小时内)
    SUM(IF(b.first_credit_law_type = '初审', a.login_t7_btch_first_loan_success_principal_24h, 0)) AS t7_loa_amt_24h,  -- T7交易额(24小时内)
    SUM(IF(b.first_credit_law_type = '初审', a.login_t30_btch_loan_success_principal, 0)) AS t30_loa_amt,              -- T30交易额
    SUM(IF(b.first_credit_law_type = '初审', a.login_t30_btch_first_loan_success_principal_24h, 0)) AS t30_loa_amt_24h, -- T30交易额(24小时内)

    -- ==================== M0转化指标(首次登录当月) ====================
    SUM(a.login_m0_apply_finish_user_count) AS sd_m0_ato_num,                                      -- 首登M0申完户数
    SUM(IF(b.first_credit_law_type = '初审', a.login_m0_btch_first_credit_user_count, 0)) AS sd_m0_adt_num,   -- 首登M0授信户数
    SUM(IF(b.first_credit_law_type = '初审', a.login_m0_btch_first_loan_apply_user_count, 0)) AS sd_m0_apl_num, -- 首登M0发起户数
    SUM(IF(b.first_credit_law_type = '初审', a.login_m0_btch_first_loan_risk_pass_user_count, 0)) AS sd_m0_rsk_num, -- 首登M0风险通过户数
    SUM(IF(b.first_credit_law_type = '初审', a.login_m0_btch_first_loan_success_user_count, 0)) AS sd_m0_loa_num,   -- 首登M0借款户数

    -- ==================== M0金额指标 ====================
    SUM(IF(b.first_credit_law_type = '初审', a.login_m0_btch_first_risk_credit_limit, 0)) AS sd_m0_adt_amt,         -- 首登M0初始授信额度
    SUM(IF(b.first_credit_law_type = '初审', a.login_m0_btch_first_loan_success_principal, 0)) AS sd_m0_loa_amt,    -- 首登M0交易额
    SUM(IF(b.first_credit_law_type = '初审', a.login_m0_btch_first_loan_success_principal_24h, 0)) AS sd_m0_loa_amt_24h -- 首登M0交易额(24小时内)

FROM
    -- 用户日期维度转化指标事实表
    (
        SELECT *
        FROM dwt.dwt_marketing_date_user_index_df_login
        WHERE ds = '${bizdate}'
    ) a

    -- 左关联用户综合信息维度表
    LEFT JOIN dwt.dwt_marketing_attribution_user_comprehensive_info_df b
        ON a.uid = b.uid
        AND b.ds = '${bizdate}'

WHERE
    -- 数据范围筛选: 2026年3月1日起
    TO_DATE(a.date_key) >= '2026-03-01'

GROUP BY
    -- 按日期、平台、渠道类别、资产类别、评分组、年龄拒绝标识分组
    a.date_key,
    b.first_login_platform_api_app_mp,
    CASE
        WHEN b.marketing_channel_group_name = '精准营销' THEN '精准营销'
        WHEN b.marketing_channel_group_name IN ('抖音', '抖音二组', '抖音中组', '抖音品专') THEN '抖音'
        WHEN b.marketing_channel_group_name IN ('微信小程序', '腾讯二组', '腾讯中组', '腾讯h5') THEN '腾讯'
        WHEN b.marketing_channel_group_name IN ('百度信息流', '快手', '百度sem', '百度sem品专', '百度sem开屏', '广点通', 'B站', '粉丝通', '穿山甲') THEN '其他信息流'
        WHEN b.marketing_channel_group_name IN ('私域获客', '行业渠道') THEN '其他CPA渠道'
        WHEN b.marketing_channel_group_name = 'API' THEN 'API'
        WHEN b.marketing_channel_group_name IN ('华为付费商店', 'OV+小米付费商店', '付费应用商店', 'VIVO信息流', '华为信息流', 'OPPO信息流', '荣耀付费商店', 'asa', '苹果付费商店') THEN '付费商店'
        WHEN b.marketing_channel_group_name IN ('自然量', '公众号') THEN '免费渠道'
        WHEN b.marketing_channel_group_name IN ('MGM') THEN 'MGM'
        ELSE '其他'
    END,
    CASE
        WHEN b.initial_risk_model_merge_a_score_group IN (1, 2, 3) THEN '安全资产'
        WHEN b.initial_risk_model_merge_a_score_group IN (4, 5, 6, 7) THEN '非安全资产'
        WHEN b.initial_risk_model_merge_a_score_group = 8 THEN '下探资产'
        ELSE NULL
    END,
    b.initial_risk_model_merge_a_score_group,
    b.is_age_refuse
;

/*******************************************************************************
 * 字段说明补充:
 *
 * 转化漏斗阶段:
 * log(登录) -> ato(申完) -> adt(授信) -> apl(发起) -> rsk(风险通过) -> loa(借款成功)
 *
 * 时间窗口说明:
 * - T0: 首次登录当天
 * - T3: 首次登录后3天内
 * - T7: 首次登录后7天内
 * - T30: 首次登录后30天内
 * - M0: 首次登录当月
 * - 24h: 24小时内完成交易
 *
 * 初审说明:
 * - first_credit_law_type='初审': 仅统计首次授信用户,排除复贷用户
 *
 * 交易户定义:
 * - 首次登录时间 = 首次借款时间(同一天)的用户
 ******************************************************************************/
