"""
参数模板管理模块
负责保存、加载和管理预算参数模板
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from core.models import BudgetParameters


class TemplateManager:
    """参数模板管理器"""

    def __init__(self, templates_dir: str = ".streamlit/templates"):
        """
        初始化模板管理器

        Args:
            templates_dir: 模板存储目录路径
        """
        self.templates_dir = Path(templates_dir)
        self.templates_dir.mkdir(parents=True, exist_ok=True)

    def save_template(
        self,
        template_name: str,
        params: BudgetParameters,
        channel_budget_shares: Dict[str, float],
        channel_1_3_rate: Dict[str, float],
        channel_1_8_cps: Dict[str, float],
        channel_t0_cost: Dict[str, float],
        non_initial_credit: float,
        existing_m0_expense: float,
        rta_promotion_fee: float,
        description: str = "",
        overwrite: bool = False,
    ) -> str:
        """
        保存参数模板

        Args:
            template_name: 模板名称
            params: 预算参数对象
            channel_1_3_rate: 渠道1-3过件率字典
            channel_1_8_cps: 渠道1-8 CPS字典
            channel_t0_cost: 渠道T0成本字典
            non_initial_credit: 非初审授信户首借交易额
            existing_m0_expense: 存量首登花费
            rta_promotion_fee: RTA费用+促申完
            description: 模板描述
            overwrite: 是否允许覆盖已有同名模板

        Returns:
            保存的模板文件路径
        """
        template_data = {
            "name": template_name,
            "description": description,
            "created_at": datetime.now().isoformat(),
            "parameters": {
                "total_budget": params.total_budget,
                "month_total_days": params.month_total_days,
                "days_elapsed": params.days_elapsed,
                "existing_m0_calculation_months": params.existing_m0_calculation_months,
                "channel_budget_shares": channel_budget_shares,
                "channel_1_3_approval_rate": channel_1_3_rate,
                "channel_1_8_cps": channel_1_8_cps,
                "channel_t0_completion_cost": channel_t0_cost,
                "non_initial_credit_transaction": non_initial_credit,
                "existing_m0_expense": existing_m0_expense,
                "rta_promotion_fee": rta_promotion_fee,
            },
        }

        # 生成安全的文件名
        safe_name = self._sanitize_filename(template_name)
        file_path = self.templates_dir / f"{safe_name}.json"

        if file_path.exists() and not overwrite:
            raise FileExistsError(f"模板 '{template_name}' 已存在")

        # 保存到JSON文件
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(template_data, f, ensure_ascii=False, indent=2)
        except IOError as e:
            raise IOError(f"模板保存失败（路径: {file_path}）：{e}") from e

        return str(file_path)

    def template_exists(self, template_name: str) -> bool:
        """检查模板是否已存在。"""
        safe_name = self._sanitize_filename(template_name)
        return (self.templates_dir / f"{safe_name}.json").exists()

    def load_template(self, template_name: str) -> Optional[Dict]:
        """
        加载参数模板

        Args:
            template_name: 模板名称

        Returns:
            模板数据字典,如果不存在则返回None
        """
        safe_name = self._sanitize_filename(template_name)
        file_path = self.templates_dir / f"{safe_name}.json"

        if not file_path.exists():
            return None

        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def list_templates(self) -> List[Dict[str, str]]:
        """
        列出所有可用的模板

        Returns:
            模板信息列表,每个元素包含name, description, created_at
        """
        templates = []
        for file_path in self.templates_dir.glob("*.json"):
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    templates.append(
                        {
                            "name": data.get("name", file_path.stem),
                            "description": data.get("description", ""),
                            "created_at": data.get("created_at", ""),
                        }
                    )
            except (json.JSONDecodeError, KeyError):
                continue

        # 按创建时间倒序排列
        templates.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        return templates

    def delete_template(self, template_name: str) -> bool:
        """
        删除指定模板

        Args:
            template_name: 模板名称

        Returns:
            是否删除成功
        """
        safe_name = self._sanitize_filename(template_name)
        file_path = self.templates_dir / f"{safe_name}.json"

        if file_path.exists():
            file_path.unlink()
            return True
        return False

    @staticmethod
    def _sanitize_filename(name: str) -> str:
        """
        清理文件名,移除不安全字符

        Args:
            name: 原始文件名

        Returns:
            安全的文件名
        """
        # 移除或替换不安全字符
        unsafe_chars = '<>:"/\\|?*'
        for char in unsafe_chars:
            name = name.replace(char, "_")
        return name.strip()
