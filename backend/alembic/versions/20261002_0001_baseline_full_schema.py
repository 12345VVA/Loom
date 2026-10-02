"""baseline: 全量 schema（squash 重建）

历史链（0001 空壳 + 0002-0017 增量）squash 为单一全量 baseline：
表结构 DDL 直接自 SQLModel.metadata 按 PostgreSQL 方言编译（38 表，
timestamptz 时间列，模型声明索引随表/独立语句）。从零部署自此走
`alembic upgrade head` 一步到位；存量库执行 `alembic stamp head`。

Revision ID: 20261002_0001
Revises:
Create Date: 2026-10-02
"""

from __future__ import annotations

from alembic import op

revision = "20261002_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
        op.execute(
            """CREATE TABLE ai_generation_task (
	id SERIAL NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	delete_time TIMESTAMP WITH TIME ZONE, 
	task_type VARCHAR(50) NOT NULL, 
	scenario VARCHAR(100) NOT NULL, 
	profile_code VARCHAR(100), 
	status VARCHAR(50) NOT NULL, 
	progress INTEGER NOT NULL, 
	request_payload VARCHAR, 
	result_payload VARCHAR, 
	error_message VARCHAR(1000), 
	celery_task_id VARCHAR(100), 
	created_by INTEGER, 
	started_at TIMESTAMP WITH TIME ZONE, 
	finished_at TIMESTAMP WITH TIME ZONE, 
	retry_count INTEGER NOT NULL, 
	PRIMARY KEY (id)
)
        """
        )
        op.execute(
            """CREATE INDEX ix_ai_generation_task_scenario ON ai_generation_task (scenario)
        """
        )
        op.execute(
            """CREATE INDEX ix_ai_generation_task_profile_code ON ai_generation_task (profile_code)
        """
        )
        op.execute(
            """CREATE INDEX ix_ai_generation_task_delete_time ON ai_generation_task (delete_time)
        """
        )
        op.execute(
            """CREATE INDEX ix_ai_generation_task_created_by ON ai_generation_task (created_by)
        """
        )
        op.execute(
            """CREATE INDEX ix_ai_generation_task_task_type ON ai_generation_task (task_type)
        """
        )
        op.execute(
            """CREATE INDEX ix_ai_generation_task_status ON ai_generation_task (status)
        """
        )
        op.execute(
            """CREATE INDEX ix_ai_generation_task_celery_task_id ON ai_generation_task (celery_task_id)
        """
        )
        op.execute(
            """CREATE TABLE ai_governance_event (
	id SERIAL NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	delete_time TIMESTAMP WITH TIME ZONE, 
	rule_id INTEGER, 
	user_id INTEGER, 
	profile_id INTEGER, 
	model_id INTEGER, 
	provider_id INTEGER, 
	event_type VARCHAR(50) NOT NULL, 
	metric VARCHAR(50) NOT NULL, 
	current_value INTEGER NOT NULL, 
	limit_value INTEGER NOT NULL, 
	window_start TIMESTAMP WITH TIME ZONE, 
	window_end TIMESTAMP WITH TIME ZONE, 
	message VARCHAR(1000), 
	notified BOOLEAN NOT NULL, 
	PRIMARY KEY (id)
)
        """
        )
        op.execute(
            """CREATE INDEX ix_ai_governance_event_profile_id ON ai_governance_event (profile_id)
        """
        )
        op.execute(
            """CREATE INDEX ix_ai_governance_event_event_type ON ai_governance_event (event_type)
        """
        )
        op.execute(
            """CREATE INDEX ix_ai_governance_event_user_id ON ai_governance_event (user_id)
        """
        )
        op.execute(
            """CREATE INDEX ix_ai_governance_event_delete_time ON ai_governance_event (delete_time)
        """
        )
        op.execute(
            """CREATE INDEX ix_ai_governance_event_window_end ON ai_governance_event (window_end)
        """
        )
        op.execute(
            """CREATE INDEX ix_ai_governance_event_notified ON ai_governance_event (notified)
        """
        )
        op.execute(
            """CREATE INDEX ix_ai_governance_event_provider_id ON ai_governance_event (provider_id)
        """
        )
        op.execute(
            """CREATE INDEX ix_ai_governance_event_model_id ON ai_governance_event (model_id)
        """
        )
        op.execute(
            """CREATE INDEX ix_ai_governance_event_rule_id ON ai_governance_event (rule_id)
        """
        )
        op.execute(
            """CREATE INDEX ix_ai_governance_event_metric ON ai_governance_event (metric)
        """
        )
        op.execute(
            """CREATE INDEX ix_ai_governance_event_window_start ON ai_governance_event (window_start)
        """
        )
        op.execute(
            """CREATE TABLE ai_governance_rule (
	id SERIAL NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	delete_time TIMESTAMP WITH TIME ZONE, 
	code VARCHAR(100) NOT NULL, 
	name VARCHAR(100) NOT NULL, 
	scope_type VARCHAR(50) NOT NULL, 
	user_id INTEGER, 
	profile_id INTEGER, 
	period VARCHAR(50) NOT NULL, 
	max_requests INTEGER, 
	max_tokens INTEGER, 
	max_cost_micro_usd INTEGER, 
	max_concurrent INTEGER, 
	mode VARCHAR(50) NOT NULL, 
	notify_enabled BOOLEAN NOT NULL, 
	is_active BOOLEAN NOT NULL, 
	sort_order INTEGER NOT NULL, 
	PRIMARY KEY (id)
)
        """
        )
        op.execute(
            """CREATE UNIQUE INDEX ix_ai_governance_rule_code ON ai_governance_rule (code)
        """
        )
        op.execute(
            """CREATE INDEX ix_ai_governance_rule_notify_enabled ON ai_governance_rule (notify_enabled)
        """
        )
        op.execute(
            """CREATE INDEX ix_ai_governance_rule_user_id ON ai_governance_rule (user_id)
        """
        )
        op.execute(
            """CREATE INDEX ix_ai_governance_rule_period ON ai_governance_rule (period)
        """
        )
        op.execute(
            """CREATE INDEX ix_ai_governance_rule_is_active ON ai_governance_rule (is_active)
        """
        )
        op.execute(
            """CREATE INDEX ix_ai_governance_rule_scope_type ON ai_governance_rule (scope_type)
        """
        )
        op.execute(
            """CREATE INDEX ix_ai_governance_rule_mode ON ai_governance_rule (mode)
        """
        )
        op.execute(
            """CREATE INDEX ix_ai_governance_rule_name ON ai_governance_rule (name)
        """
        )
        op.execute(
            """CREATE INDEX ix_ai_governance_rule_sort_order ON ai_governance_rule (sort_order)
        """
        )
        op.execute(
            """CREATE INDEX ix_ai_governance_rule_delete_time ON ai_governance_rule (delete_time)
        """
        )
        op.execute(
            """CREATE INDEX ix_ai_governance_rule_profile_id ON ai_governance_rule (profile_id)
        """
        )
        op.execute(
            """CREATE TABLE ai_model (
	id SERIAL NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	delete_time TIMESTAMP WITH TIME ZONE, 
	provider_id INTEGER NOT NULL, 
	code VARCHAR(150) NOT NULL, 
	name VARCHAR(150) NOT NULL, 
	model_type VARCHAR(50) NOT NULL, 
	capabilities VARCHAR, 
	context_window INTEGER, 
	max_output_tokens INTEGER, 
	pricing_config VARCHAR, 
	default_config VARCHAR, 
	is_active BOOLEAN NOT NULL, 
	sort_order INTEGER NOT NULL, 
	PRIMARY KEY (id)
)
        """
        )
        op.execute(
            """CREATE INDEX ix_ai_model_model_type ON ai_model (model_type)
        """
        )
        op.execute(
            """CREATE INDEX ix_ai_model_sort_order ON ai_model (sort_order)
        """
        )
        op.execute(
            """CREATE INDEX ix_ai_model_name ON ai_model (name)
        """
        )
        op.execute(
            """CREATE INDEX ix_ai_model_delete_time ON ai_model (delete_time)
        """
        )
        op.execute(
            """CREATE INDEX ix_ai_model_code ON ai_model (code)
        """
        )
        op.execute(
            """CREATE INDEX ix_ai_model_is_active ON ai_model (is_active)
        """
        )
        op.execute(
            """CREATE INDEX ix_ai_model_provider_id ON ai_model (provider_id)
        """
        )
        op.execute(
            """CREATE TABLE ai_model_call_log (
	id SERIAL NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	delete_time TIMESTAMP WITH TIME ZONE, 
	provider_id INTEGER, 
	model_id INTEGER, 
	profile_id INTEGER, 
	user_id INTEGER, 
	scenario VARCHAR(100), 
	model_type VARCHAR(50) NOT NULL, 
	status VARCHAR(50) NOT NULL, 
	latency_ms INTEGER NOT NULL, 
	prompt_tokens INTEGER NOT NULL, 
	completion_tokens INTEGER NOT NULL, 
	total_tokens INTEGER NOT NULL, 
	cost_micro_usd INTEGER NOT NULL, 
	currency VARCHAR(20) NOT NULL, 
	error_message VARCHAR(500), 
	request_id VARCHAR(100), 
	workflow_instance_id INTEGER, 
	request_options VARCHAR, 
	PRIMARY KEY (id)
)
        """
        )
        op.execute(
            """CREATE INDEX ix_ai_model_call_log_profile_id ON ai_model_call_log (profile_id)
        """
        )
        op.execute(
            """CREATE INDEX ix_ai_model_call_log_scenario ON ai_model_call_log (scenario)
        """
        )
        op.execute(
            """CREATE INDEX ix_ai_model_call_log_workflow_instance_id ON ai_model_call_log (workflow_instance_id)
        """
        )
        op.execute(
            """CREATE INDEX ix_ai_model_call_log_created_at ON ai_model_call_log (created_at)
        """
        )
        op.execute(
            """CREATE INDEX ix_ai_model_call_log_model_type ON ai_model_call_log (model_type)
        """
        )
        op.execute(
            """CREATE INDEX ix_ai_model_call_log_request_id ON ai_model_call_log (request_id)
        """
        )
        op.execute(
            """CREATE INDEX ix_ai_model_call_log_status_created_at ON ai_model_call_log (status, created_at)
        """
        )
        op.execute(
            """CREATE INDEX ix_ai_model_call_log_model_id ON ai_model_call_log (model_id)
        """
        )
        op.execute(
            """CREATE INDEX ix_ai_model_call_log_model_id_created_at ON ai_model_call_log (model_id, created_at)
        """
        )
        op.execute(
            """CREATE INDEX ix_ai_model_call_log_user_id_created_at ON ai_model_call_log (user_id, created_at)
        """
        )
        op.execute(
            """CREATE INDEX ix_ai_model_call_log_delete_time ON ai_model_call_log (delete_time)
        """
        )
        op.execute(
            """CREATE INDEX ix_ai_model_call_log_status ON ai_model_call_log (status)
        """
        )
        op.execute(
            """CREATE INDEX ix_ai_model_call_log_user_id ON ai_model_call_log (user_id)
        """
        )
        op.execute(
            """CREATE INDEX ix_ai_model_call_log_provider_id ON ai_model_call_log (provider_id)
        """
        )
        op.execute(
            """CREATE TABLE ai_model_profile (
	id SERIAL NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	delete_time TIMESTAMP WITH TIME ZONE, 
	code VARCHAR(100) NOT NULL, 
	name VARCHAR(100) NOT NULL, 
	model_id INTEGER NOT NULL, 
	scenario VARCHAR(100) NOT NULL, 
	temperature FLOAT, 
	top_p FLOAT, 
	max_tokens INTEGER, 
	response_format VARCHAR, 
	tools_config VARCHAR, 
	timeout INTEGER, 
	retry_count INTEGER NOT NULL, 
	retry_delay_seconds INTEGER NOT NULL, 
	fallback_profile_id INTEGER, 
	is_default BOOLEAN NOT NULL, 
	is_active BOOLEAN NOT NULL, 
	sort_order INTEGER NOT NULL, 
	PRIMARY KEY (id)
)
        """
        )
        op.execute(
            """CREATE INDEX ix_ai_model_profile_model_id ON ai_model_profile (model_id)
        """
        )
        op.execute(
            """CREATE INDEX ix_ai_model_profile_scenario ON ai_model_profile (scenario)
        """
        )
        op.execute(
            """CREATE INDEX ix_ai_model_profile_is_active ON ai_model_profile (is_active)
        """
        )
        op.execute(
            """CREATE INDEX ix_ai_model_profile_fallback_profile_id ON ai_model_profile (fallback_profile_id)
        """
        )
        op.execute(
            """CREATE INDEX ix_ai_model_profile_name ON ai_model_profile (name)
        """
        )
        op.execute(
            """CREATE INDEX ix_ai_model_profile_sort_order ON ai_model_profile (sort_order)
        """
        )
        op.execute(
            """CREATE INDEX ix_ai_model_profile_is_default ON ai_model_profile (is_default)
        """
        )
        op.execute(
            """CREATE INDEX ix_ai_model_profile_delete_time ON ai_model_profile (delete_time)
        """
        )
        op.execute(
            """CREATE UNIQUE INDEX ix_ai_model_profile_code ON ai_model_profile (code)
        """
        )
        op.execute(
            """CREATE TABLE ai_provider (
	id SERIAL NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	delete_time TIMESTAMP WITH TIME ZONE, 
	code VARCHAR(100) NOT NULL, 
	name VARCHAR(100) NOT NULL, 
	adapter VARCHAR(50) NOT NULL, 
	base_url VARCHAR(500), 
	api_key_cipher VARCHAR, 
	api_key_mask VARCHAR(100), 
	admin_access_key_cipher VARCHAR, 
	admin_secret_key_cipher VARCHAR, 
	admin_access_key_mask VARCHAR(100), 
	extra_config VARCHAR, 
	is_active BOOLEAN NOT NULL, 
	sort_order INTEGER NOT NULL, 
	PRIMARY KEY (id)
)
        """
        )
        op.execute(
            """CREATE UNIQUE INDEX ix_ai_provider_code ON ai_provider (code)
        """
        )
        op.execute(
            """CREATE INDEX ix_ai_provider_is_active ON ai_provider (is_active)
        """
        )
        op.execute(
            """CREATE INDEX ix_ai_provider_sort_order ON ai_provider (sort_order)
        """
        )
        op.execute(
            """CREATE INDEX ix_ai_provider_name ON ai_provider (name)
        """
        )
        op.execute(
            """CREATE INDEX ix_ai_provider_adapter ON ai_provider (adapter)
        """
        )
        op.execute(
            """CREATE INDEX ix_ai_provider_delete_time ON ai_provider (delete_time)
        """
        )
        op.execute(
            """CREATE TABLE ai_runtime_invocation (
	id SERIAL NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	delete_time TIMESTAMP WITH TIME ZONE, 
	invocation_id VARCHAR(100) NOT NULL, 
	user_id INTEGER, 
	profile_id INTEGER, 
	model_id INTEGER, 
	provider_id INTEGER, 
	status VARCHAR(50) NOT NULL, 
	started_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	finished_at TIMESTAMP WITH TIME ZONE, 
	task_id INTEGER, 
	cc_keys VARCHAR(500), 
	PRIMARY KEY (id)
)
        """
        )
        op.execute(
            """CREATE INDEX ix_ai_runtime_invocation_model_id ON ai_runtime_invocation (model_id)
        """
        )
        op.execute(
            """CREATE INDEX ix_ai_runtime_invocation_started_at ON ai_runtime_invocation (started_at)
        """
        )
        op.execute(
            """CREATE INDEX ix_ai_runtime_invocation_delete_time ON ai_runtime_invocation (delete_time)
        """
        )
        op.execute(
            """CREATE INDEX ix_ai_runtime_invocation_profile_id ON ai_runtime_invocation (profile_id)
        """
        )
        op.execute(
            """CREATE INDEX ix_ai_runtime_invocation_provider_id ON ai_runtime_invocation (provider_id)
        """
        )
        op.execute(
            """CREATE INDEX ix_ai_runtime_invocation_status ON ai_runtime_invocation (status)
        """
        )
        op.execute(
            """CREATE INDEX ix_ai_runtime_invocation_finished_at ON ai_runtime_invocation (finished_at)
        """
        )
        op.execute(
            """CREATE INDEX ix_ai_runtime_invocation_user_id ON ai_runtime_invocation (user_id)
        """
        )
        op.execute(
            """CREATE INDEX ix_ai_runtime_invocation_task_id ON ai_runtime_invocation (task_id)
        """
        )
        op.execute(
            """CREATE UNIQUE INDEX ix_ai_runtime_invocation_invocation_id ON ai_runtime_invocation (invocation_id)
        """
        )
        op.execute(
            """CREATE TABLE dict_info (
	id SERIAL NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	delete_time TIMESTAMP WITH TIME ZONE, 
	type_id INTEGER NOT NULL, 
	parent_id INTEGER, 
	name VARCHAR NOT NULL, 
	value VARCHAR NOT NULL, 
	sort_order INTEGER NOT NULL, 
	remark VARCHAR, 
	PRIMARY KEY (id)
)
        """
        )
        op.execute(
            """CREATE INDEX ix_dict_info_parent_id ON dict_info (parent_id)
        """
        )
        op.execute(
            """CREATE INDEX ix_dict_info_type_id ON dict_info (type_id)
        """
        )
        op.execute(
            """CREATE INDEX ix_dict_info_delete_time ON dict_info (delete_time)
        """
        )
        op.execute(
            """CREATE TABLE dict_type (
	id SERIAL NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	delete_time TIMESTAMP WITH TIME ZONE, 
	name VARCHAR NOT NULL, 
	key VARCHAR NOT NULL, 
	PRIMARY KEY (id)
)
        """
        )
        op.execute(
            """CREATE UNIQUE INDEX ix_dict_type_key ON dict_type (key)
        """
        )
        op.execute(
            """CREATE INDEX ix_dict_type_delete_time ON dict_type (delete_time)
        """
        )
        op.execute(
            """CREATE INDEX ix_dict_type_name ON dict_type (name)
        """
        )
        op.execute(
            """CREATE TABLE media_asset (
	id SERIAL NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	delete_time TIMESTAMP WITH TIME ZONE, 
	asset_type VARCHAR(50) NOT NULL, 
	source_type VARCHAR(50) NOT NULL, 
	source_task_id INTEGER, 
	provider_code VARCHAR(100), 
	model_code VARCHAR(150), 
	profile_code VARCHAR(100), 
	original_url TEXT, 
	storage_url VARCHAR(1000), 
	file_name VARCHAR(255), 
	mime_type VARCHAR(100), 
	md5 VARCHAR(32), 
	size_bytes INTEGER NOT NULL, 
	width INTEGER, 
	height INTEGER, 
	duration_seconds FLOAT, 
	prompt VARCHAR, 
	params_payload VARCHAR, 
	status VARCHAR(50) NOT NULL, 
	error_message VARCHAR(1000), 
	created_by INTEGER, 
	workflow_instance_id INTEGER, 
	workflow_definition_id INTEGER, 
	workflow_node_id VARCHAR(100), 
	PRIMARY KEY (id)
)
        """
        )
        op.execute(
            """CREATE INDEX ix_media_asset_created_by ON media_asset (created_by)
        """
        )
        op.execute(
            """CREATE INDEX ix_media_asset_workflow_instance_id ON media_asset (workflow_instance_id)
        """
        )
        op.execute(
            """CREATE INDEX ix_media_asset_status ON media_asset (status)
        """
        )
        op.execute(
            """CREATE INDEX ix_media_asset_provider_code ON media_asset (provider_code)
        """
        )
        op.execute(
            """CREATE INDEX ix_media_asset_source_task_id ON media_asset (source_task_id)
        """
        )
        op.execute(
            """CREATE INDEX ix_media_asset_delete_time ON media_asset (delete_time)
        """
        )
        op.execute(
            """CREATE INDEX ix_media_asset_source_type ON media_asset (source_type)
        """
        )
        op.execute(
            """CREATE INDEX ix_media_asset_model_code ON media_asset (model_code)
        """
        )
        op.execute(
            """CREATE INDEX ix_media_asset_storage_url ON media_asset (storage_url)
        """
        )
        op.execute(
            """CREATE INDEX ix_media_asset_file_name ON media_asset (file_name)
        """
        )
        op.execute(
            """CREATE INDEX ix_media_asset_asset_type ON media_asset (asset_type)
        """
        )
        op.execute(
            """CREATE INDEX ix_media_asset_md5 ON media_asset (md5)
        """
        )
        op.execute(
            """CREATE INDEX ix_media_asset_mime_type ON media_asset (mime_type)
        """
        )
        op.execute(
            """CREATE INDEX ix_media_asset_profile_code ON media_asset (profile_code)
        """
        )
        op.execute(
            """CREATE TABLE notification_message (
	id SERIAL NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	delete_time TIMESTAMP WITH TIME ZONE, 
	title VARCHAR(200) NOT NULL, 
	content VARCHAR NOT NULL, 
	message_type VARCHAR NOT NULL, 
	level VARCHAR NOT NULL, 
	source_module VARCHAR, 
	business_key VARCHAR, 
	link_url VARCHAR, 
	send_status VARCHAR NOT NULL, 
	scheduled_at TIMESTAMP WITH TIME ZONE, 
	expired_at TIMESTAMP WITH TIME ZONE, 
	sender_id INTEGER, 
	is_recalled BOOLEAN NOT NULL, 
	recalled_at TIMESTAMP WITH TIME ZONE, 
	recalled_by INTEGER, 
	PRIMARY KEY (id)
)
        """
        )
        op.execute(
            """CREATE INDEX ix_notification_message_source_module ON notification_message (source_module)
        """
        )
        op.execute(
            """CREATE INDEX ix_notification_message_business_key ON notification_message (business_key)
        """
        )
        op.execute(
            """CREATE INDEX ix_notification_message_send_status ON notification_message (send_status)
        """
        )
        op.execute(
            """CREATE INDEX ix_notification_message_title ON notification_message (title)
        """
        )
        op.execute(
            """CREATE INDEX ix_notification_message_message_type ON notification_message (message_type)
        """
        )
        op.execute(
            """CREATE INDEX ix_notification_message_level ON notification_message (level)
        """
        )
        op.execute(
            """CREATE INDEX ix_notification_message_sender_id ON notification_message (sender_id)
        """
        )
        op.execute(
            """CREATE INDEX ix_notification_message_recalled_by ON notification_message (recalled_by)
        """
        )
        op.execute(
            """CREATE INDEX ix_notification_message_is_recalled ON notification_message (is_recalled)
        """
        )
        op.execute(
            """CREATE INDEX ix_notification_message_delete_time ON notification_message (delete_time)
        """
        )
        op.execute(
            """CREATE TABLE notification_recipient (
	id SERIAL NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	delete_time TIMESTAMP WITH TIME ZONE, 
	message_id INTEGER NOT NULL, 
	user_id INTEGER NOT NULL, 
	role_id INTEGER, 
	department_id INTEGER, 
	tenant_id INTEGER, 
	is_read BOOLEAN NOT NULL, 
	read_time TIMESTAMP WITH TIME ZONE, 
	is_archived BOOLEAN NOT NULL, 
	is_deleted BOOLEAN NOT NULL, 
	PRIMARY KEY (id)
)
        """
        )
        op.execute(
            """CREATE INDEX ix_notification_recipient_department_id ON notification_recipient (department_id)
        """
        )
        op.execute(
            """CREATE INDEX ix_notification_recipient_tenant_id ON notification_recipient (tenant_id)
        """
        )
        op.execute(
            """CREATE INDEX ix_notification_recipient_role_id ON notification_recipient (role_id)
        """
        )
        op.execute(
            """CREATE INDEX ix_notification_recipient_user_id ON notification_recipient (user_id)
        """
        )
        op.execute(
            """CREATE INDEX ix_notification_recipient_message_id ON notification_recipient (message_id)
        """
        )
        op.execute(
            """CREATE INDEX ix_notification_recipient_is_deleted ON notification_recipient (is_deleted)
        """
        )
        op.execute(
            """CREATE INDEX ix_notification_recipient_is_archived ON notification_recipient (is_archived)
        """
        )
        op.execute(
            """CREATE INDEX ix_notification_recipient_is_read ON notification_recipient (is_read)
        """
        )
        op.execute(
            """CREATE INDEX ix_notification_recipient_delete_time ON notification_recipient (delete_time)
        """
        )
        op.execute(
            """CREATE TABLE notification_rule (
	id SERIAL NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	delete_time TIMESTAMP WITH TIME ZONE, 
	code VARCHAR(100) NOT NULL, 
	name VARCHAR(100) NOT NULL, 
	users VARCHAR, 
	roles VARCHAR, 
	departments VARCHAR, 
	tenants VARCHAR, 
	include_child_departments BOOLEAN NOT NULL, 
	all_admins BOOLEAN NOT NULL, 
	condition VARCHAR, 
	is_active BOOLEAN NOT NULL, 
	PRIMARY KEY (id)
)
        """
        )
        op.execute(
            """CREATE UNIQUE INDEX ix_notification_rule_code ON notification_rule (code)
        """
        )
        op.execute(
            """CREATE INDEX ix_notification_rule_delete_time ON notification_rule (delete_time)
        """
        )
        op.execute(
            """CREATE INDEX ix_notification_rule_name ON notification_rule (name)
        """
        )
        op.execute(
            """CREATE TABLE notification_template (
	id SERIAL NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	delete_time TIMESTAMP WITH TIME ZONE, 
	code VARCHAR(100) NOT NULL, 
	name VARCHAR(100) NOT NULL, 
	title_template VARCHAR NOT NULL, 
	content_template VARCHAR NOT NULL, 
	default_level VARCHAR NOT NULL, 
	default_link_url VARCHAR, 
	is_active BOOLEAN NOT NULL, 
	PRIMARY KEY (id)
)
        """
        )
        op.execute(
            """CREATE UNIQUE INDEX ix_notification_template_code ON notification_template (code)
        """
        )
        op.execute(
            """CREATE INDEX ix_notification_template_is_active ON notification_template (is_active)
        """
        )
        op.execute(
            """CREATE INDEX ix_notification_template_delete_time ON notification_template (delete_time)
        """
        )
        op.execute(
            """CREATE INDEX ix_notification_template_name ON notification_template (name)
        """
        )
        op.execute(
            """CREATE TABLE sys_department (
	id SERIAL NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	delete_time TIMESTAMP WITH TIME ZONE, 
	name VARCHAR NOT NULL, 
	parent_id INTEGER, 
	sort_order INTEGER NOT NULL, 
	is_active BOOLEAN NOT NULL, 
	PRIMARY KEY (id)
)
        """
        )
        op.execute(
            """CREATE INDEX ix_sys_department_delete_time ON sys_department (delete_time)
        """
        )
        op.execute(
            """CREATE UNIQUE INDEX ix_sys_department_name ON sys_department (name)
        """
        )
        op.execute(
            """CREATE TABLE sys_log (
	id SERIAL NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	delete_time TIMESTAMP WITH TIME ZONE, 
	user_id INTEGER, 
	action VARCHAR NOT NULL, 
	method VARCHAR NOT NULL, 
	params VARCHAR, 
	ip VARCHAR, 
	ip_addr VARCHAR, 
	status INTEGER NOT NULL, 
	message VARCHAR, 
	PRIMARY KEY (id)
)
        """
        )
        op.execute(
            """CREATE INDEX ix_sys_log_delete_time ON sys_log (delete_time)
        """
        )
        op.execute(
            """CREATE INDEX ix_sys_log_user_id ON sys_log (user_id)
        """
        )
        op.execute(
            """CREATE INDEX ix_sys_log_action ON sys_log (action)
        """
        )
        op.execute(
            """CREATE INDEX ix_sys_log_method ON sys_log (method)
        """
        )
        op.execute(
            """CREATE TABLE sys_login_log (
	id SERIAL NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	delete_time TIMESTAMP WITH TIME ZONE, 
	user_id INTEGER, 
	name VARCHAR, 
	account VARCHAR, 
	login_type VARCHAR NOT NULL, 
	status INTEGER NOT NULL, 
	ip VARCHAR, 
	risk_hit INTEGER NOT NULL, 
	reason VARCHAR, 
	client_type VARCHAR, 
	device_id VARCHAR, 
	source_system VARCHAR, 
	user_agent VARCHAR, 
	PRIMARY KEY (id)
)
        """
        )
        op.execute(
            """CREATE INDEX ix_sys_login_log_delete_time ON sys_login_log (delete_time)
        """
        )
        op.execute(
            """CREATE INDEX ix_sys_login_log_account ON sys_login_log (account)
        """
        )
        op.execute(
            """CREATE INDEX ix_sys_login_log_login_type ON sys_login_log (login_type)
        """
        )
        op.execute(
            """CREATE INDEX ix_sys_login_log_user_id ON sys_login_log (user_id)
        """
        )
        op.execute(
            """CREATE TABLE sys_menu (
	id SERIAL NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	delete_time TIMESTAMP WITH TIME ZONE, 
	parent_id INTEGER, 
	name VARCHAR NOT NULL, 
	code VARCHAR NOT NULL, 
	type VARCHAR NOT NULL, 
	path VARCHAR, 
	component VARCHAR, 
	icon VARCHAR, 
	keep_alive BOOLEAN NOT NULL, 
	is_show BOOLEAN NOT NULL, 
	permission VARCHAR, 
	sort_order INTEGER NOT NULL, 
	is_active BOOLEAN NOT NULL, 
	PRIMARY KEY (id)
)
        """
        )
        op.execute(
            """CREATE INDEX ix_sys_menu_delete_time ON sys_menu (delete_time)
        """
        )
        op.execute(
            """CREATE INDEX ix_sys_menu_permission ON sys_menu (permission)
        """
        )
        op.execute(
            """CREATE UNIQUE INDEX ix_sys_menu_code ON sys_menu (code)
        """
        )
        op.execute(
            """CREATE TABLE sys_param (
	id SERIAL NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	delete_time TIMESTAMP WITH TIME ZONE, 
	name VARCHAR NOT NULL, 
	key_name VARCHAR NOT NULL, 
	data VARCHAR, 
	data_type INTEGER NOT NULL, 
	remark VARCHAR, 
	PRIMARY KEY (id)
)
        """
        )
        op.execute(
            """CREATE INDEX ix_sys_param_delete_time ON sys_param (delete_time)
        """
        )
        op.execute(
            """CREATE UNIQUE INDEX ix_sys_param_key_name ON sys_param (key_name)
        """
        )
        op.execute(
            """CREATE INDEX ix_sys_param_name ON sys_param (name)
        """
        )
        op.execute(
            """CREATE TABLE sys_role (
	id SERIAL NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	delete_time TIMESTAMP WITH TIME ZONE, 
	name VARCHAR NOT NULL, 
	code VARCHAR NOT NULL, 
	label VARCHAR NOT NULL, 
	remark VARCHAR, 
	data_scope VARCHAR NOT NULL, 
	is_active BOOLEAN NOT NULL, 
	PRIMARY KEY (id)
)
        """
        )
        op.execute(
            """CREATE INDEX ix_sys_role_delete_time ON sys_role (delete_time)
        """
        )
        op.execute(
            """CREATE UNIQUE INDEX ix_sys_role_name ON sys_role (name)
        """
        )
        op.execute(
            """CREATE UNIQUE INDEX ix_sys_role_code ON sys_role (code)
        """
        )
        op.execute(
            """CREATE UNIQUE INDEX ix_sys_role_label ON sys_role (label)
        """
        )
        op.execute(
            """CREATE TABLE sys_role_department (
	id SERIAL NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	delete_time TIMESTAMP WITH TIME ZONE, 
	role_id INTEGER NOT NULL, 
	department_id INTEGER NOT NULL, 
	PRIMARY KEY (id)
)
        """
        )
        op.execute(
            """CREATE INDEX ix_sys_role_department_delete_time ON sys_role_department (delete_time)
        """
        )
        op.execute(
            """CREATE INDEX ix_sys_role_department_department_id ON sys_role_department (department_id)
        """
        )
        op.execute(
            """CREATE INDEX ix_sys_role_department_role_id ON sys_role_department (role_id)
        """
        )
        op.execute(
            """CREATE TABLE sys_role_menu (
	id SERIAL NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	delete_time TIMESTAMP WITH TIME ZONE, 
	role_id INTEGER NOT NULL, 
	menu_id INTEGER NOT NULL, 
	PRIMARY KEY (id)
)
        """
        )
        op.execute(
            """CREATE INDEX ix_sys_role_menu_delete_time ON sys_role_menu (delete_time)
        """
        )
        op.execute(
            """CREATE INDEX ix_sys_role_menu_role_id ON sys_role_menu (role_id)
        """
        )
        op.execute(
            """CREATE INDEX ix_sys_role_menu_menu_id ON sys_role_menu (menu_id)
        """
        )
        op.execute(
            """CREATE TABLE sys_security_log (
	id SERIAL NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	delete_time TIMESTAMP WITH TIME ZONE, 
	operator_id INTEGER NOT NULL, 
	operator_name VARCHAR NOT NULL, 
	operator_ip VARCHAR, 
	target_type VARCHAR NOT NULL, 
	target_id INTEGER, 
	target_name VARCHAR, 
	operation VARCHAR NOT NULL, 
	module VARCHAR NOT NULL, 
	resource_path VARCHAR, 
	old_value VARCHAR, 
	new_value VARCHAR, 
	diff_data VARCHAR, 
	business_type VARCHAR, 
	request_id VARCHAR, 
	status INTEGER NOT NULL, 
	error_message VARCHAR, 
	remark VARCHAR, 
	PRIMARY KEY (id)
)
        """
        )
        op.execute(
            """CREATE INDEX ix_sys_security_log_target_id ON sys_security_log (target_id)
        """
        )
        op.execute(
            """CREATE INDEX ix_sys_security_log_operator_id ON sys_security_log (operator_id)
        """
        )
        op.execute(
            """CREATE INDEX ix_sys_security_log_request_id ON sys_security_log (request_id)
        """
        )
        op.execute(
            """CREATE INDEX ix_sys_security_log_operation ON sys_security_log (operation)
        """
        )
        op.execute(
            """CREATE INDEX ix_sys_security_log_module ON sys_security_log (module)
        """
        )
        op.execute(
            """CREATE INDEX ix_sys_security_log_status ON sys_security_log (status)
        """
        )
        op.execute(
            """CREATE INDEX ix_sys_security_log_target_type ON sys_security_log (target_type)
        """
        )
        op.execute(
            """CREATE INDEX ix_sys_security_log_operator_name ON sys_security_log (operator_name)
        """
        )
        op.execute(
            """CREATE INDEX ix_sys_security_log_delete_time ON sys_security_log (delete_time)
        """
        )
        op.execute(
            """CREATE TABLE sys_user (
	id SERIAL NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	delete_time TIMESTAMP WITH TIME ZONE, 
	username VARCHAR NOT NULL, 
	full_name VARCHAR NOT NULL, 
	nick_name VARCHAR, 
	head_img VARCHAR, 
	email VARCHAR, 
	phone VARCHAR, 
	remark VARCHAR, 
	password_hash VARCHAR NOT NULL, 
	password_version INTEGER NOT NULL, 
	password_changed_at TIMESTAMP WITH TIME ZONE, 
	department_id INTEGER, 
	is_super_admin BOOLEAN NOT NULL, 
	is_manager BOOLEAN NOT NULL, 
	is_department_leader BOOLEAN NOT NULL, 
	is_active BOOLEAN NOT NULL, 
	last_login_at TIMESTAMP WITH TIME ZONE, 
	PRIMARY KEY (id)
)
        """
        )
        op.execute(
            """CREATE INDEX ix_sys_user_delete_time ON sys_user (delete_time)
        """
        )
        op.execute(
            """CREATE UNIQUE INDEX ix_sys_user_username ON sys_user (username)
        """
        )
        op.execute(
            """CREATE UNIQUE INDEX ix_sys_user_email ON sys_user (email)
        """
        )
        op.execute(
            """CREATE TABLE sys_user_role (
	id SERIAL NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	delete_time TIMESTAMP WITH TIME ZONE, 
	user_id INTEGER NOT NULL, 
	role_id INTEGER NOT NULL, 
	PRIMARY KEY (id)
)
        """
        )
        op.execute(
            """CREATE INDEX ix_sys_user_role_role_id ON sys_user_role (role_id)
        """
        )
        op.execute(
            """CREATE INDEX ix_sys_user_role_user_id ON sys_user_role (user_id)
        """
        )
        op.execute(
            """CREATE INDEX ix_sys_user_role_delete_time ON sys_user_role (delete_time)
        """
        )
        op.execute(
            """CREATE TABLE task_info (
	id SERIAL NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	delete_time TIMESTAMP WITH TIME ZONE, 
	job_id VARCHAR, 
	repeat_conf VARCHAR, 
	name VARCHAR NOT NULL, 
	cron VARCHAR, 
	"limit" INTEGER, 
	every INTEGER, 
	remark VARCHAR, 
	status INTEGER NOT NULL, 
	start_date TIMESTAMP WITH TIME ZONE, 
	end_date TIMESTAMP WITH TIME ZONE, 
	data VARCHAR, 
	service VARCHAR, 
	type INTEGER NOT NULL, 
	next_run_time TIMESTAMP WITH TIME ZONE, 
	task_type INTEGER NOT NULL, 
	last_execute_time TIMESTAMP WITH TIME ZONE, 
	notify_enabled BOOLEAN NOT NULL, 
	notify_on_success BOOLEAN NOT NULL, 
	notify_on_failure BOOLEAN NOT NULL, 
	notify_on_timeout BOOLEAN NOT NULL, 
	notify_recipients VARCHAR, 
	notify_template_code VARCHAR, 
	notify_timeout_ms INTEGER NOT NULL, 
	PRIMARY KEY (id)
)
        """
        )
        op.execute(
            """CREATE INDEX ix_task_info_delete_time ON task_info (delete_time)
        """
        )
        op.execute(
            """CREATE INDEX ix_task_info_name ON task_info (name)
        """
        )
        op.execute(
            """CREATE INDEX ix_task_info_job_id ON task_info (job_id)
        """
        )
        op.execute(
            """CREATE TABLE task_log (
	id SERIAL NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	delete_time TIMESTAMP WITH TIME ZONE, 
	task_id INTEGER NOT NULL, 
	status INTEGER NOT NULL, 
	detail VARCHAR, 
	consume_time INTEGER NOT NULL, 
	PRIMARY KEY (id)
)
        """
        )
        op.execute(
            """CREATE INDEX ix_task_log_delete_time ON task_log (delete_time)
        """
        )
        op.execute(
            """CREATE INDEX ix_task_log_task_id ON task_log (task_id)
        """
        )
        op.execute(
            """CREATE TABLE workflow_annotation (
	id SERIAL NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	delete_time TIMESTAMP WITH TIME ZONE, 
	case_result_id INTEGER NOT NULL, 
	annotator_user_id INTEGER, 
	label VARCHAR(20) NOT NULL, 
	score FLOAT, 
	reason VARCHAR(500), 
	is_gold BOOLEAN NOT NULL, 
	PRIMARY KEY (id)
)
        """
        )
        op.execute(
            """CREATE INDEX ix_workflow_annotation_delete_time ON workflow_annotation (delete_time)
        """
        )
        op.execute(
            """CREATE INDEX ix_workflow_annotation_is_gold ON workflow_annotation (is_gold)
        """
        )
        op.execute(
            """CREATE INDEX ix_workflow_annotation_case_result_id ON workflow_annotation (case_result_id)
        """
        )
        op.execute(
            """CREATE INDEX ix_workflow_annotation_annotator_user_id ON workflow_annotation (annotator_user_id)
        """
        )
        op.execute(
            """CREATE TABLE workflow_artifact (
	id SERIAL NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	delete_time TIMESTAMP WITH TIME ZONE, 
	instance_id INTEGER NOT NULL, 
	definition_id INTEGER NOT NULL, 
	version_id INTEGER, 
	node_id VARCHAR(100), 
	user_id INTEGER, 
	field_key VARCHAR(150) NOT NULL, 
	field_path VARCHAR(200), 
	asset_type VARCHAR(20) NOT NULL, 
	media_asset_id INTEGER, 
	storage_url VARCHAR(1000), 
	original_url VARCHAR(1000), 
	content VARCHAR, 
	content_ref VARCHAR(500), 
	PRIMARY KEY (id)
)
        """
        )
        op.execute(
            """CREATE INDEX ix_workflow_artifact_instance_id ON workflow_artifact (instance_id)
        """
        )
        op.execute(
            """CREATE INDEX ix_workflow_artifact_delete_time ON workflow_artifact (delete_time)
        """
        )
        op.execute(
            """CREATE INDEX ix_workflow_artifact_asset_type ON workflow_artifact (asset_type)
        """
        )
        op.execute(
            """CREATE INDEX ix_workflow_artifact_media_asset_id ON workflow_artifact (media_asset_id)
        """
        )
        op.execute(
            """CREATE INDEX ix_workflow_artifact_user_id ON workflow_artifact (user_id)
        """
        )
        op.execute(
            """CREATE INDEX ix_workflow_artifact_definition_id ON workflow_artifact (definition_id)
        """
        )
        op.execute(
            """CREATE TABLE workflow_definition (
	id SERIAL NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	delete_time TIMESTAMP WITH TIME ZONE, 
	code VARCHAR(100) NOT NULL, 
	name VARCHAR(150) NOT NULL, 
	description VARCHAR(500), 
	current_version_id INTEGER, 
	draft_version_id INTEGER, 
	is_active BOOLEAN NOT NULL, 
	user_id INTEGER, 
	PRIMARY KEY (id)
)
        """
        )
        op.execute(
            """CREATE INDEX ix_workflow_definition_user_id ON workflow_definition (user_id)
        """
        )
        op.execute(
            """CREATE INDEX ix_workflow_definition_draft_version_id ON workflow_definition (draft_version_id)
        """
        )
        op.execute(
            """CREATE INDEX ix_workflow_definition_name ON workflow_definition (name)
        """
        )
        op.execute(
            """CREATE INDEX ix_workflow_definition_current_version_id ON workflow_definition (current_version_id)
        """
        )
        op.execute(
            """CREATE INDEX ix_workflow_definition_is_active ON workflow_definition (is_active)
        """
        )
        op.execute(
            """CREATE INDEX ix_workflow_definition_delete_time ON workflow_definition (delete_time)
        """
        )
        op.execute(
            """CREATE UNIQUE INDEX ix_workflow_definition_code ON workflow_definition (code)
        """
        )
        op.execute(
            """CREATE TABLE workflow_definition_version (
	id SERIAL NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	delete_time TIMESTAMP WITH TIME ZONE, 
	definition_id INTEGER NOT NULL, 
	version_no INTEGER NOT NULL, 
	status VARCHAR(20) NOT NULL, 
	graph_json VARCHAR(100000) NOT NULL, 
	change_note VARCHAR(500), 
	parent_version_id INTEGER, 
	published_at TIMESTAMP WITH TIME ZONE, 
	published_by INTEGER, 
	user_id INTEGER, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_workflow_def_version_def_no UNIQUE (definition_id, version_no)
)
        """
        )
        op.execute(
            """CREATE INDEX ix_workflow_definition_version_user_id ON workflow_definition_version (user_id)
        """
        )
        op.execute(
            """CREATE INDEX ix_workflow_definition_version_published_by ON workflow_definition_version (published_by)
        """
        )
        op.execute(
            """CREATE INDEX ix_workflow_definition_version_delete_time ON workflow_definition_version (delete_time)
        """
        )
        op.execute(
            """CREATE INDEX ix_workflow_definition_version_definition_id ON workflow_definition_version (definition_id)
        """
        )
        op.execute(
            """CREATE INDEX ix_workflow_definition_version_status ON workflow_definition_version (status)
        """
        )
        op.execute(
            """CREATE INDEX ix_workflow_definition_version_parent_version_id ON workflow_definition_version (parent_version_id)
        """
        )
        op.execute(
            """CREATE TABLE workflow_eval_case_result (
	id SERIAL NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	delete_time TIMESTAMP WITH TIME ZONE, 
	eval_run_id INTEGER NOT NULL, 
	test_case_id INTEGER, 
	case_key VARCHAR(100) NOT NULL, 
	input_data VARCHAR NOT NULL, 
	actual_output VARCHAR, 
	actual_output_storage_ref VARCHAR(500), 
	expected_output VARCHAR, 
	score FLOAT NOT NULL, 
	passed BOOLEAN NOT NULL, 
	latency_ms INTEGER NOT NULL, 
	token_total INTEGER NOT NULL, 
	cost_micro_usd INTEGER NOT NULL, 
	status VARCHAR(50) NOT NULL, 
	evaluator_type VARCHAR(50) NOT NULL, 
	evaluator_detail VARCHAR, 
	error_message VARCHAR(1000), 
	workflow_instance_id INTEGER, 
	tags VARCHAR, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_workflow_eval_case_result_run_case_key UNIQUE (eval_run_id, case_key)
)
        """
        )
        op.execute(
            """CREATE INDEX ix_workflow_eval_case_result_latency_ms ON workflow_eval_case_result (latency_ms)
        """
        )
        op.execute(
            """CREATE INDEX ix_workflow_eval_case_result_eval_run_id_latency_ms ON workflow_eval_case_result (eval_run_id, latency_ms)
        """
        )
        op.execute(
            """CREATE INDEX ix_workflow_eval_case_result_score ON workflow_eval_case_result (score)
        """
        )
        op.execute(
            """CREATE INDEX ix_workflow_eval_case_result_workflow_instance_id ON workflow_eval_case_result (workflow_instance_id)
        """
        )
        op.execute(
            """CREATE INDEX ix_workflow_eval_case_result_test_case_id ON workflow_eval_case_result (test_case_id)
        """
        )
        op.execute(
            """CREATE INDEX ix_workflow_eval_case_result_status ON workflow_eval_case_result (status)
        """
        )
        op.execute(
            """CREATE INDEX ix_workflow_eval_case_result_eval_run_id_case_key ON workflow_eval_case_result (eval_run_id, case_key)
        """
        )
        op.execute(
            """CREATE INDEX ix_workflow_eval_case_result_delete_time ON workflow_eval_case_result (delete_time)
        """
        )
        op.execute(
            """CREATE INDEX ix_workflow_eval_case_result_passed ON workflow_eval_case_result (passed)
        """
        )
        op.execute(
            """CREATE INDEX ix_workflow_eval_case_result_case_key ON workflow_eval_case_result (case_key)
        """
        )
        op.execute(
            """CREATE INDEX ix_workflow_eval_case_result_eval_run_id ON workflow_eval_case_result (eval_run_id)
        """
        )
        op.execute(
            """CREATE TABLE workflow_eval_run (
	id SERIAL NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	delete_time TIMESTAMP WITH TIME ZONE, 
	test_set_id INTEGER NOT NULL, 
	definition_id INTEGER, 
	graph_json_snapshot VARCHAR NOT NULL, 
	definition_version_id INTEGER, 
	test_set_snapshot VARCHAR, 
	version_label VARCHAR(100), 
	status VARCHAR(50) NOT NULL, 
	total INTEGER NOT NULL, 
	passed INTEGER NOT NULL, 
	failed INTEGER NOT NULL, 
	errored INTEGER NOT NULL, 
	avg_score FLOAT NOT NULL, 
	pass_rate FLOAT NOT NULL, 
	p50_latency_ms INTEGER NOT NULL, 
	p95_latency_ms INTEGER NOT NULL, 
	p99_latency_ms INTEGER NOT NULL, 
	max_latency_ms INTEGER NOT NULL, 
	total_tokens INTEGER NOT NULL, 
	total_cost_micro_usd INTEGER NOT NULL, 
	summary_payload VARCHAR, 
	started_at TIMESTAMP WITH TIME ZONE, 
	finished_at TIMESTAMP WITH TIME ZONE, 
	error_message VARCHAR(1000), 
	celery_task_id VARCHAR(200), 
	user_id INTEGER, 
	PRIMARY KEY (id)
)
        """
        )
        op.execute(
            """CREATE INDEX ix_workflow_eval_run_user_id ON workflow_eval_run (user_id)
        """
        )
        op.execute(
            """CREATE INDEX ix_workflow_eval_run_definition_version_id ON workflow_eval_run (definition_version_id)
        """
        )
        op.execute(
            """CREATE INDEX ix_workflow_eval_run_definition_id ON workflow_eval_run (definition_id)
        """
        )
        op.execute(
            """CREATE INDEX ix_workflow_eval_run_test_set_id_created_at ON workflow_eval_run (test_set_id, created_at)
        """
        )
        op.execute(
            """CREATE INDEX ix_workflow_eval_run_delete_time ON workflow_eval_run (delete_time)
        """
        )
        op.execute(
            """CREATE INDEX ix_workflow_eval_run_status ON workflow_eval_run (status)
        """
        )
        op.execute(
            """CREATE INDEX ix_workflow_eval_run_celery_task_id ON workflow_eval_run (celery_task_id)
        """
        )
        op.execute(
            """CREATE INDEX ix_workflow_eval_run_test_set_id ON workflow_eval_run (test_set_id)
        """
        )
        op.execute(
            """CREATE TABLE workflow_eval_test_case (
	id SERIAL NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	delete_time TIMESTAMP WITH TIME ZONE, 
	test_set_id INTEGER NOT NULL, 
	case_key VARCHAR(100) NOT NULL, 
	input_data VARCHAR NOT NULL, 
	expected_output VARCHAR, 
	expected_text VARCHAR(2000), 
	evaluator_config VARCHAR, 
	weight FLOAT NOT NULL, 
	sort_order INTEGER NOT NULL, 
	tags VARCHAR, 
	PRIMARY KEY (id)
)
        """
        )
        op.execute(
            """CREATE INDEX ix_workflow_eval_test_case_case_key ON workflow_eval_test_case (case_key)
        """
        )
        op.execute(
            """CREATE INDEX ix_workflow_eval_test_case_delete_time ON workflow_eval_test_case (delete_time)
        """
        )
        op.execute(
            """CREATE INDEX ix_workflow_eval_test_case_test_set_id ON workflow_eval_test_case (test_set_id)
        """
        )
        op.execute(
            """CREATE INDEX ix_workflow_eval_test_case_test_set_id_case_key ON workflow_eval_test_case (test_set_id, case_key)
        """
        )
        op.execute(
            """CREATE TABLE workflow_eval_test_set (
	id SERIAL NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	delete_time TIMESTAMP WITH TIME ZONE, 
	name VARCHAR(150) NOT NULL, 
	description VARCHAR(500), 
	definition_id INTEGER, 
	items_count INTEGER NOT NULL, 
	tags VARCHAR, 
	user_id INTEGER, 
	PRIMARY KEY (id)
)
        """
        )
        op.execute(
            """CREATE INDEX ix_workflow_eval_test_set_user_id ON workflow_eval_test_set (user_id)
        """
        )
        op.execute(
            """CREATE INDEX ix_workflow_eval_test_set_definition_id ON workflow_eval_test_set (definition_id)
        """
        )
        op.execute(
            """CREATE INDEX ix_workflow_eval_test_set_delete_time ON workflow_eval_test_set (delete_time)
        """
        )
        op.execute(
            """CREATE INDEX ix_workflow_eval_test_set_name ON workflow_eval_test_set (name)
        """
        )
        op.execute(
            """CREATE TABLE workflow_execution_log (
	id SERIAL NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	delete_time TIMESTAMP WITH TIME ZONE, 
	instance_id INTEGER NOT NULL, 
	node_id VARCHAR(100) NOT NULL, 
	node_name VARCHAR(150) NOT NULL, 
	node_type VARCHAR(50) NOT NULL, 
	input_data VARCHAR(100000) NOT NULL, 
	output_data VARCHAR(100000) NOT NULL, 
	latency_ms INTEGER NOT NULL, 
	status VARCHAR(50) NOT NULL, 
	error_message VARCHAR(1000), 
	payload_type VARCHAR(20) NOT NULL, 
	diff_base_log_id INTEGER, 
	input_storage_ref VARCHAR(500), 
	output_storage_ref VARCHAR(500), 
	PRIMARY KEY (id)
)
        """
        )
        op.execute(
            """CREATE INDEX ix_workflow_execution_log_delete_time ON workflow_execution_log (delete_time)
        """
        )
        op.execute(
            """CREATE INDEX ix_workflow_execution_log_node_id ON workflow_execution_log (node_id)
        """
        )
        op.execute(
            """CREATE INDEX ix_workflow_execution_log_instance_id ON workflow_execution_log (instance_id)
        """
        )
        op.execute(
            """CREATE INDEX ix_workflow_execution_log_instance_id_created_at ON workflow_execution_log (instance_id, created_at)
        """
        )
        op.execute(
            """CREATE INDEX ix_workflow_execution_log_diff_base_log_id ON workflow_execution_log (diff_base_log_id)
        """
        )
        op.execute(
            """CREATE TABLE workflow_instance (
	id SERIAL NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	delete_time TIMESTAMP WITH TIME ZONE, 
	definition_id INTEGER NOT NULL, 
	version_id INTEGER, 
	thread_id VARCHAR(100) NOT NULL, 
	status VARCHAR(50) NOT NULL, 
	current_node VARCHAR(100), 
	state_data VARCHAR(100000) NOT NULL, 
	state_data_ref VARCHAR(500), 
	error_message VARCHAR(1000), 
	celery_task_id VARCHAR(200), 
	user_id INTEGER, 
	failed_node_id VARCHAR(100), 
	PRIMARY KEY (id)
)
        """
        )
        op.execute(
            """CREATE INDEX ix_workflow_instance_user_id ON workflow_instance (user_id)
        """
        )
        op.execute(
            """CREATE INDEX ix_workflow_instance_version_id ON workflow_instance (version_id)
        """
        )
        op.execute(
            """CREATE INDEX ix_workflow_instance_celery_task_id ON workflow_instance (celery_task_id)
        """
        )
        op.execute(
            """CREATE INDEX ix_workflow_instance_definition_id_created_at ON workflow_instance (definition_id, created_at)
        """
        )
        op.execute(
            """CREATE INDEX ix_workflow_instance_status ON workflow_instance (status)
        """
        )
        op.execute(
            """CREATE INDEX ix_workflow_instance_thread_id ON workflow_instance (thread_id)
        """
        )
        op.execute(
            """CREATE INDEX ix_workflow_instance_delete_time ON workflow_instance (delete_time)
        """
        )
        op.execute(
            """CREATE INDEX ix_workflow_instance_definition_id ON workflow_instance (definition_id)
        """
        )


def downgrade() -> None:
    """baseline 无降级（全量重建由 manage.py rebuild 承担）。"""
    pass
