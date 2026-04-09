"""Patch wireframe_full_v3.html: replace results section with restructured version."""
import pathlib

html_path = pathlib.Path(__file__).parent / "wireframe_full_v3.html"
content = html_path.read_text(encoding="utf-8")

start_marker = '<hr class="divider">'
end_marker = '<!-- ================================================================ -->\n<!-- PAGE MMM:'

start_idx = content.index(start_marker)
end_idx = content.index(end_marker)

before = content[:start_idx]
after = content[end_idx:]

new_section = """<hr class="divider">

  <!-- ══════════ RESULTS: 总 (Summary First) ══════════ -->

  <!-- Decision Summary -->
  <div class="section">
    <div class="card" style="background: linear-gradient(135deg, #E8F5E9 0%, #fff 100%);">
      <div class="card-title" style="font-size: 16px;">&#128203; 决策摘要</div>
      <div style="font-size: 14px; line-height: 2; margin-top: 8px;">
        本次预算 <strong>3,000 万元</strong>，预计整体首借交易额 <strong>2.35 亿元</strong>，全业务 CPS <strong>35.3%</strong>。
      </div>
      <div style="margin-top: 12px; display: flex; gap: 8px; flex-wrap: wrap;">
        <span style="background:var(--accent-light);color:var(--accent);padding:4px 12px;border-radius:4px;font-size:12px;font-weight:600;">&#10003; 预算已分配完毕</span>
        <span style="background:var(--accent-light);color:var(--accent);padding:4px 12px;border-radius:4px;font-size:12px;font-weight:600;">&#10003; CPS 低于上月</span>
        <span style="background:var(--warning-light);color:#e65100;padding:4px 12px;border-radius:4px;font-size:12px;font-weight:600;">&#9888; MMM 预测交易额低于 V01 约 15%</span>
      </div>
      <div style="margin-top: 16px; padding-top: 12px; border-top: 1px solid var(--border);">
        <div style="font-size: 13px; font-weight: 600; margin-bottom: 8px;">关键结论</div>
        <ul style="font-size: 13px; line-height: 2; padding-left: 18px; color: #333;">
          <li>精准营销 ROI 3.1x 全渠道最高且仅 45% 饱和，<strong style="color:var(--accent)">建议优先增投</strong></li>
          <li>抖音饱和度 89%，V01 线性外推高估其贡献约 6.5pp，<strong style="color:var(--danger)">建议控量</strong></li>
          <li>双引擎预测区间：借款金额 <strong>7,200 ~ 8,500 万元</strong>，建议取中值规划</li>
          <li>全业务 CPS 35.3% 较上月 33.1% 上升 2.2pp，主因抖音成本上行</li>
        </ul>
      </div>
    </div>
  </div>

  <!-- Core Metrics -->
  <div class="metrics section">
    <div class="metric-card"><div class="metric-label">总投放花费</div><div class="metric-value">3,000 <span style="font-size:12px">万元</span></div></div>
    <div class="metric-card"><div class="metric-label">整体首借交易额</div><div class="metric-value">2.35 <span style="font-size:12px">亿元</span></div><div class="metric-delta delta-up">+0.12 vs 上月</div></div>
    <div class="metric-card"><div class="metric-label">全业务CPS</div><div class="metric-value">35.3%</div><div class="metric-delta delta-down">+2.2pp vs 上月</div></div>
    <div class="metric-card"><div class="metric-label">T0交易额</div><div class="metric-value">1.82 <span style="font-size:12px">亿元</span></div></div>
    <div class="metric-card"><div class="metric-label">1-3 T0过件率</div><div class="metric-value">23.8%</div></div>
  </div>

  <!-- Key Charts (总览图表直接展示) -->
  <div class="section">
    <div class="card">
      <div class="card-title">预算结构与效率总览</div>
      <div class="chart-row">
        <div class="chart">
          [渠道花费分布饼图]<br>
          腾讯 38.3% | 抖音 35.0% | 精准 20.7% | 付费 6.0%
        </div>
        <div class="chart">
          [渠道交易额贡献柱状图]<br>
          各渠道 T0交易额(深色) + M0交易额(浅色) 堆叠<br>
          红虚线标注上月交易额作为对比
        </div>
      </div>
      <div class="chart">
        [预算结构 vs 交易贡献 对比条/Sankey]<br>
        左: 花费占比 | 右: 交易额占比 | 连线展示效率差异<br>
        精准营销: 花费 20.7% 贡献 26.8% &#8594; 效率最高 | 抖音: 花费 35.0% 贡献 28.2% &#8594; 效率偏低
      </div>
    </div>
  </div>

  <!-- 历史达成与当月预估 (折叠) -->
  <details class="collapse-card section">
    <summary>历史达成与当月预估 (点击展开)</summary>
    <div class="collapse-body" style="padding-top:16px;">
      <div class="card-desc">对比近3个月历史实际达成与本次当月预估，观察趋势变化和预估合理性。</div>
      <table>
        <thead>
          <tr>
            <th>指标</th>
            <th class="col-r">2025-08<br><span style="font-size:10px;color:var(--text-muted)">实际</span></th>
            <th class="col-r">2025-09<br><span style="font-size:10px;color:var(--text-muted)">实际</span></th>
            <th class="col-r">2025-10<br><span style="font-size:10px;color:var(--text-muted)">实际</span></th>
            <th class="col-r" style="background:var(--info-light);font-weight:700">2025-11<br><span style="font-size:10px">当月预估</span></th>
            <th class="col-r">vs 上月</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td><strong>总花费 (万元)</strong></td>
            <td class="col-r">2,720</td><td class="col-r">2,780</td><td class="col-r">2,850</td>
            <td class="col-r" style="background:var(--info-light);font-weight:600">3,000</td>
            <td class="col-r delta-up">+5.3%</td>
          </tr>
          <tr>
            <td><strong>首借交易额 (亿元)</strong></td>
            <td class="col-r">2.08</td><td class="col-r">2.15</td><td class="col-r">2.23</td>
            <td class="col-r" style="background:var(--info-light);font-weight:600">2.35</td>
            <td class="col-r delta-up">+5.4%</td>
          </tr>
          <tr>
            <td><strong>全业务CPS</strong></td>
            <td class="col-r">32.5%</td><td class="col-r">32.8%</td><td class="col-r">33.1%</td>
            <td class="col-r" style="background:var(--info-light);font-weight:600">35.3%</td>
            <td class="col-r delta-down">+2.2pp</td>
          </tr>
          <tr>
            <td><strong>1-3过件率</strong></td>
            <td class="col-r">22.0%</td><td class="col-r">22.3%</td><td class="col-r">22.5%</td>
            <td class="col-r" style="background:var(--info-light);font-weight:600">23.8%</td>
            <td class="col-r delta-up">+1.3pp</td>
          </tr>
          <tr>
            <td><strong>T0交易额 (亿元)</strong></td>
            <td class="col-r">1.58</td><td class="col-r">1.65</td><td class="col-r">1.72</td>
            <td class="col-r" style="background:var(--info-light);font-weight:600">1.82</td>
            <td class="col-r delta-up">+5.8%</td>
          </tr>
          <tr>
            <td><strong>腾讯花费 (万元)</strong></td>
            <td class="col-r">950</td><td class="col-r">980</td><td class="col-r">1,034</td>
            <td class="col-r" style="background:var(--info-light)">1,150</td>
            <td class="col-r delta-up">+11.2%</td>
          </tr>
          <tr>
            <td><strong>抖音花费 (万元)</strong></td>
            <td class="col-r">1,100</td><td class="col-r">1,200</td><td class="col-r">1,329</td>
            <td class="col-r" style="background:var(--info-light)">1,050</td>
            <td class="col-r delta-down">-21.0%</td>
          </tr>
          <tr>
            <td><strong>精准营销花费 (万元)</strong></td>
            <td class="col-r">400</td><td class="col-r">420</td><td class="col-r">468</td>
            <td class="col-r" style="background:var(--info-light)">620</td>
            <td class="col-r delta-up">+32.5%</td>
          </tr>
        </tbody>
      </table>
      <div class="chart-row" style="margin-top: 16px;">
        <div class="chart chart-sm">
          [月度花费 vs 交易额趋势折线图]<br>
          双Y轴: 左=花费(万元) 右=交易额(亿元)<br>
          虚线段=当月预估 | 实线=历史实际
        </div>
        <div class="chart chart-sm">
          [CPS + 过件率月度走势]<br>
          双折线: CPS(红) + 过件率(蓝)<br>
          注意 CPS 11月预估上升趋势
        </div>
      </div>
      <div class="callout callout-warn" style="margin-top: 12px;">
        <strong>趋势提示：</strong>CPS 连续4个月上升 (32.5% &#8594; 35.3%)，主因抖音成本持续走高。本次预估通过减少抖音(-21%)、增加精准营销(+32.5%)试图改善效率。
      </div>
    </div>
  </details>

  <!-- ══════════ RESULTS: 分 (Detail Tabs) ══════════ -->
  <div class="section-label">分项详情</div>

  <!-- Result Tabs -->
  <div class="tabs" id="result-tabs">
    <div class="tab active" onclick="switchTab('result',0)">&#128202; 渠道结果</div>
    <div class="tab" onclick="switchTab('result',1)">&#128101; 客群结果</div>
    <div class="tab" onclick="switchTab('result',2)">&#128290; 系数追溯</div>
    <div class="tab" onclick="switchTab('result',3)">&#128190; 方案管理</div>
    <div class="tab tab-new" onclick="switchTab('result',4)">&#129302; 模型对照 <span class="badge badge-new">NEW</span></div>
  </div>

  <!-- Result Tab 0: Channel Result -->
  <div class="tab-panel active" id="result-tab-0">
    <div class="card">
      <div class="callout callout-info" style="margin-bottom:16px">
        <strong>渠道核心结论：</strong>精准营销 CPS 15.0% 全渠道最低且交易额贡献率最高(花费占比20.7% 贡献26.8%)。抖音 CPS 30.0% 偏高，建议下月继续优化结构。
      </div>
      <div class="card-title">渠道结果 (Table 1)</div>
      <table>
        <thead>
          <tr><th>渠道</th><th class="col-r">花费(万)</th><th class="col-r">花费结构</th><th class="col-r">T0交易额(亿)</th><th class="col-r">M0交易额(亿)</th><th class="col-r">1-3过件率</th><th class="col-r">CPS</th><th class="col-r">申完量</th><th class="col-r">申完结构</th></tr>
        </thead>
        <tbody>
          <tr><td><strong>腾讯</strong></td><td class="col-r">1,150</td><td class="col-r">38.3%</td><td class="col-r">0.43</td><td class="col-r">0.64</td><td class="col-r">24.0%</td><td class="col-r">27.0%</td><td class="col-r">12,500</td><td class="col-r">40.2%</td></tr>
          <tr><td><strong>抖音</strong></td><td class="col-r">1,050</td><td class="col-r">35.0%</td><td class="col-r">0.35</td><td class="col-r">0.53</td><td class="col-r">20.0%</td><td class="col-r" style="color:var(--danger)">30.0%</td><td class="col-r">9,800</td><td class="col-r">31.5%</td></tr>
          <tr><td><strong>精准营销</strong></td><td class="col-r">620</td><td class="col-r">20.7%</td><td class="col-r">0.41</td><td class="col-r">0.62</td><td class="col-r">18.0%</td><td class="col-r" style="color:var(--accent);font-weight:600">15.0%</td><td class="col-r">5,600</td><td class="col-r">18.0%</td></tr>
          <tr><td><strong>付费商店</strong></td><td class="col-r">180</td><td class="col-r">6.0%</td><td class="col-r">0.18</td><td class="col-r">0.27</td><td class="col-r">7.0%</td><td class="col-r">10.0%</td><td class="col-r">3,200</td><td class="col-r">10.3%</td></tr>
          <tr class="row-total"><td>总计</td><td class="col-r">3,000</td><td class="col-r">100%</td><td class="col-r">1.37</td><td class="col-r">2.06</td><td class="col-r">-</td><td class="col-r">-</td><td class="col-r">31,100</td><td class="col-r">100%</td></tr>
        </tbody>
      </table>
      <div class="chart-row" style="margin-top:16px">
        <div class="chart chart-sm">[渠道花费 vs T0交易额 散点图]<br>气泡大小=申完量, 颜色=CPS高低</div>
        <div class="chart chart-sm">[渠道 CPS 对比柱状图]<br>红线=上月均值 作为基准参考</div>
      </div>
    </div>
  </div>

  <!-- Result Tab 1: Customer Group Result -->
  <div class="tab-panel" id="result-tab-1">
    <div class="card">
      <div class="callout callout-info" style="margin-bottom:16px">
        <strong>客群核心结论：</strong>整体首借交易额 2.35 亿元，其中初审占 66%(1.55亿)、非初审占 34%(0.80亿)。当月首登M0贡献最大(0.75亿)，存量M0 CPS 34.4% 处于合理区间。
      </div>
      <div class="card-title">客群结果 (Table 2)</div>
      <div class="chart" style="margin-bottom:16px">[客群交易额瀑布图]<br>当月首登M0(0.75) + 存量M0(0.35) + M1+(0.45) + 非初审(0.80) = 2.35 亿</div>
      <table>
        <thead><tr><th style="width:300px">指标</th><th class="col-r">交易额(亿元)</th><th class="col-r">花费(万元)</th><th>效率指标</th></tr></thead>
        <tbody>
          <tr class="indent-0"><td class="indent-0">整体首借交易额</td><td class="col-r"><strong>2.35</strong></td><td class="col-r">3,200</td><td>全业务CPS=35.3%</td></tr>
          <tr><td class="indent-1">1) 初审授信户首借交易额</td><td class="col-r">1.55</td><td class="col-r"></td><td></td></tr>
          <tr><td class="indent-2">A. 当月首登初审M0交易额</td><td class="col-r">0.75</td><td class="col-r"></td><td></td></tr>
          <tr><td class="indent-3">- 首登T0交易额</td><td class="col-r">0.45</td><td class="col-r"></td><td></td></tr>
          <tr><td class="indent-3">- M0补充交易额</td><td class="col-r">0.30</td><td class="col-r"></td><td></td></tr>
          <tr><td class="indent-2">B. 存量首登初审M0交易额</td><td class="col-r">0.35</td><td class="col-r">1,200</td><td>存量CPS=34.3%</td></tr>
          <tr><td class="indent-2">C. 初审M1+交易额</td><td class="col-r">0.45</td><td class="col-r"></td><td></td></tr>
          <tr><td class="indent-1">2) 非初审授信户首借交易额</td><td class="col-r">0.80</td><td class="col-r"></td><td></td></tr>
          <tr><td class="indent-2">- 非初审-重申</td><td class="col-r">0.50</td><td class="col-r"></td><td></td></tr>
          <tr><td class="indent-2">- 非初审-重审及其他</td><td class="col-r">0.30</td><td class="col-r"></td><td></td></tr>
          <tr class="indent-sep"><td class="indent-sep" colspan="4">--- 费用汇总 ---</td></tr>
          <tr><td class="indent-1">投放花费</td><td class="col-r"></td><td class="col-r">3,000</td><td></td></tr>
          <tr><td class="indent-1">RTA费用+促申完</td><td class="col-r"></td><td class="col-r">200</td><td></td></tr>
          <tr class="indent-sep"><td class="indent-sep" colspan="4">--- 效率指标 ---</td></tr>
          <tr><td class="indent-1">全业务CPS</td><td class="col-r"></td><td class="col-r"></td><td><strong>35.3%</strong></td></tr>
          <tr><td class="indent-1">1-3组T0过件率（排年龄）</td><td class="col-r"></td><td class="col-r"></td><td><strong>23.8%</strong></td></tr>
        </tbody>
      </table>
    </div>
  </div>

  <!-- Result Tab 2: Coefficient Trace -->
  <div class="tab-panel" id="result-tab-2">
    <div class="card">
      <div class="card-title">系数追溯</div>
      <div class="card-desc">展示 M0/T0 比值系数和存量首登 CPS 的历史计算过程，增强结果可解释性。</div>
      <div class="two-col">
        <div>
          <div style="font-size:13px;font-weight:600;margin-bottom:8px;">M0/T0 交易比值系数（6月均值）</div>
          <table>
            <thead><tr><th>月份</th><th class="col-r">M0交易额</th><th class="col-r">T0交易额</th><th class="col-r">比值</th></tr></thead>
            <tbody>
              <tr><td>2025-05</td><td class="col-r">0.60</td><td class="col-r">0.40</td><td class="col-r">1.50</td></tr>
              <tr><td>2025-06</td><td class="col-r">0.55</td><td class="col-r">0.38</td><td class="col-r">1.45</td></tr>
              <tr><td>2025-07</td><td class="col-r">0.63</td><td class="col-r">0.42</td><td class="col-r">1.50</td></tr>
              <tr><td>2025-08</td><td class="col-r">0.58</td><td class="col-r">0.39</td><td class="col-r">1.49</td></tr>
              <tr><td>2025-09</td><td class="col-r">0.62</td><td class="col-r">0.41</td><td class="col-r">1.51</td></tr>
              <tr><td>2025-10</td><td class="col-r">0.65</td><td class="col-r">0.43</td><td class="col-r">1.51</td></tr>
              <tr class="row-total"><td>均值</td><td class="col-r"></td><td class="col-r"></td><td class="col-r"><strong>1.49</strong></td></tr>
            </tbody>
          </table>
        </div>
        <div>
          <div style="font-size:13px;font-weight:600;margin-bottom:8px;">存量首登M0 CPS（3月均值）</div>
          <table>
            <thead><tr><th>月份</th><th class="col-r">存量花费(万)</th><th class="col-r">存量M0交易额(亿)</th><th class="col-r">CPS</th></tr></thead>
            <tbody>
              <tr><td>2025-08</td><td class="col-r">420</td><td class="col-r">0.12</td><td class="col-r">35.0%</td></tr>
              <tr><td>2025-09</td><td class="col-r">435</td><td class="col-r">0.13</td><td class="col-r">33.5%</td></tr>
              <tr><td>2025-10</td><td class="col-r">450</td><td class="col-r">0.13</td><td class="col-r">34.6%</td></tr>
              <tr class="row-total"><td>均值</td><td class="col-r"></td><td class="col-r"></td><td class="col-r"><strong>34.4%</strong></td></tr>
            </tbody>
          </table>
          <div class="chart chart-sm" style="margin-top:12px">[CPS 近月折线图 + 均值线]<br>3月/6月窗口均值对比</div>
        </div>
      </div>
    </div>
  </div>

  <!-- Result Tab 3: Scenario Manager -->
  <div class="tab-panel" id="result-tab-3">
    <div class="card">
      <div class="card-title">方案管理</div>
      <div class="card-desc">保存当前结果为方案，与历史方案进行对比。</div>
      <div style="display: flex; gap: 12px; margin-bottom: 16px;">
        <input style="flex:1; padding: 8px 12px; border: 1px solid var(--border); border-radius: 6px;" placeholder="输入方案名称，如：4月基准方案">
        <button class="btn btn-primary btn-sm">&#128190; 保存方案</button>
      </div>
      <table>
        <thead><tr><th>方案</th><th class="col-r">总花费</th><th class="col-r">交易额</th><th class="col-r">CPS</th><th class="col-r">过件率</th><th>时间</th><th class="col-c">操作</th></tr></thead>
        <tbody>
          <tr style="background:#fffde7"><td><strong>当前方案</strong> <span class="badge" style="background:#FF9800;color:#fff">未保存</span></td><td class="col-r">3,000</td><td class="col-r">2.35</td><td class="col-r">35.3%</td><td class="col-r">23.8%</td><td>-</td><td class="col-c">-</td></tr>
          <tr><td>4月基准方案</td><td class="col-r">3,000</td><td class="col-r">2.35</td><td class="col-r">35.3%</td><td class="col-r">23.8%</td><td>04-07 14:30</td><td class="col-c"><button class="btn btn-ghost btn-sm">对比</button> <button class="btn btn-sm btn-secondary">加载</button></td></tr>
          <tr><td>3月实际方案</td><td class="col-r">2,850</td><td class="col-r">2.23</td><td class="col-r">33.1%</td><td class="col-r">22.5%</td><td>03-05 10:15</td><td class="col-c"><button class="btn btn-ghost btn-sm">对比</button> <button class="btn btn-sm btn-secondary">加载</button></td></tr>
          <tr><td>3月激进方案</td><td class="col-r">3,200</td><td class="col-r">2.48</td><td class="col-r">37.2%</td><td class="col-r">24.1%</td><td>03-03 16:45</td><td class="col-c"><button class="btn btn-ghost btn-sm">对比</button> <button class="btn btn-sm btn-secondary">加载</button></td></tr>
        </tbody>
      </table>
      <div style="margin-top:20px;">
        <div style="font-size:13px;font-weight:600;margin-bottom:8px;">方案对比: 4月基准 vs 3月实际</div>
        <table class="cmp">
          <thead><tr><th>指标</th><th>4月基准</th><th>3月实际</th><th>差异</th></tr></thead>
          <tbody>
            <tr><td>总花费</td><td>3,000</td><td>2,850</td><td class="diff-good">+5.3%</td></tr>
            <tr><td>交易额</td><td class="best">2.35</td><td>2.23</td><td class="diff-good">+5.4%</td></tr>
            <tr><td>CPS</td><td>35.3%</td><td class="best">33.1%</td><td class="diff-bad">+2.2pp</td></tr>
            <tr><td>过件率</td><td class="best">23.8%</td><td>22.5%</td><td class="diff-good">+1.3pp</td></tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>

  <!-- Result Tab 4: Model Comparison (NEW) -->
  <div class="tab-panel" id="result-tab-4">
    <div class="card" style="border: 2px solid var(--info);">
      <div class="card-title">&#129302; 模型对照 - V01 规则层 vs MMM 模型层 <span class="badge badge-new">NEW</span></div>
      <div class="card-desc">同一花费方案下，两套引擎的预测结果对比。差异越大说明线性假设偏差越大。</div>

      <div class="callout callout-info" style="margin-bottom:16px">
        <strong>对照核心结论：</strong>V01 借款金额预测比 MMM 高 15%，主因抖音渠道线性外推偏差。建议取双引擎区间中值规划。
      </div>

      <table class="cmp">
        <thead>
          <tr><th>指标</th><th style="width:130px">V01 规则层</th><th style="width:130px">MMM 模型层</th><th style="width:90px">差异</th><th style="text-align:left;width:260px">解读</th></tr>
        </thead>
        <tbody>
          <tr><td>总花费 (万元)</td><td>3,000</td><td>3,000</td><td style="color:var(--text-muted)">-</td><td style="text-align:left;font-size:12px;color:var(--text-muted)">输入一致</td></tr>
          <tr><td>预测借款金额 (万元)</td><td class="best">8,500</td><td>7,200</td><td class="diff-bad">-15.3%</td><td style="text-align:left;font-size:12px">V01 线性外推可能高估，MMM 考虑饱和效应</td></tr>
          <tr><td>预测CPS</td><td>35.3%</td><td class="best">41.7%</td><td class="diff-bad">+6.4pp</td><td style="text-align:left;font-size:12px">MMM 认为实际成本更高（渠道饱和导致）</td></tr>
          <tr><td>腾讯贡献占比</td><td>38.3%</td><td class="best">42.1%</td><td class="diff-good">+3.8pp</td><td style="text-align:left;font-size:12px">腾讯效率被 V01 低估</td></tr>
          <tr><td>抖音贡献占比</td><td class="best">35.0%</td><td>28.5%</td><td class="diff-bad">-6.5pp</td><td style="text-align:left;font-size:12px;color:var(--danger)">抖音饱和，实际贡献低于线性预期</td></tr>
          <tr><td>精准营销贡献占比</td><td>20.7%</td><td class="best">24.4%</td><td class="diff-good">+3.7pp</td><td style="text-align:left;font-size:12px;color:var(--accent)">ROI最高渠道被 V01 低估</td></tr>
        </tbody>
      </table>

      <div class="chart-row" style="margin-top: 20px;">
        <div class="chart">
          [渠道贡献对比柱状图]<br>
          左柱: V01 各渠道交易额占比<br>
          右柱: MMM 各渠道贡献占比<br>
          高亮差异最大的渠道（抖音、精准营销）
        </div>
        <div class="chart">
          [预测区间可视化]<br>
          借款金额: V01=8,500 ← 真实预期 &#8594; MMM=7,200<br>
          CPS: V01=35.3% ← 真实预期 &#8594; MMM=41.7%<br>
          建议取区间中值作为规划基准
        </div>
      </div>

      <div style="display: flex; gap: 12px; margin-top: 16px;">
        <button class="btn btn-ghost">&#128202; 查看各渠道详细响应曲线</button>
        <button class="btn btn-ghost">&#128229; 导出双引擎对比报告</button>
      </div>
    </div>
  </div>

</div>


"""

result = before + new_section + after
html_path.write_text(result, encoding="utf-8")
print(f"Done. {len(result)} chars written.")
