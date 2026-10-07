declare namespace Eps {
	interface dashboard {
		/**
		 * 任意键值
		 */
		[key: string]: any;
	}

	interface governance_event {
		/**
		 * id
		 */
		id?: number;

		/**
		 * rule_id
		 */
		ruleId?: number;

		/**
		 * rule_name
		 */
		ruleName?: string;

		/**
		 * user_id
		 */
		userId?: number;

		/**
		 * username
		 */
		username?: string;

		/**
		 * profile_id
		 */
		profileId?: number;

		/**
		 * profile_name
		 */
		profileName?: string;

		/**
		 * model_id
		 */
		modelId?: number;

		/**
		 * model_name
		 */
		modelName?: string;

		/**
		 * provider_id
		 */
		providerId?: number;

		/**
		 * provider_name
		 */
		providerName?: string;

		/**
		 * event_type
		 */
		eventType?: string;

		/**
		 * metric
		 */
		metric?: string;

		/**
		 * current_value
		 */
		currentValue?: number;

		/**
		 * limit_value
		 */
		limitValue?: number;

		/**
		 * window_start
		 */
		windowStart?: Date;

		/**
		 * window_end
		 */
		windowEnd?: Date;

		/**
		 * message
		 */
		message?: string;

		/**
		 * notified
		 */
		notified?: boolean;

		/**
		 * created_at
		 */
		createTime?: Date;

		/**
		 * updated_at
		 */
		updateTime?: Date;

		/**
		 * 任意键值
		 */
		[key: string]: any;
	}

	interface governance_rule {
		/**
		 * id
		 */
		id?: number;

		/**
		 * code
		 */
		code?: string;

		/**
		 * name
		 */
		name?: string;

		/**
		 * scope_type
		 */
		scopeType?: string;

		/**
		 * user_id
		 */
		userId?: number;

		/**
		 * username
		 */
		username?: string;

		/**
		 * profile_id
		 */
		profileId?: number;

		/**
		 * profile_name
		 */
		profileName?: string;

		/**
		 * period
		 */
		period?: string;

		/**
		 * max_requests
		 */
		maxRequests?: number;

		/**
		 * max_tokens
		 */
		maxTokens?: number;

		/**
		 * max_cost_micro_usd
		 */
		maxCostMicroUsd?: number;

		/**
		 * max_concurrent
		 */
		maxConcurrent?: number;

		/**
		 * mode
		 */
		mode?: string;

		/**
		 * notify_enabled
		 */
		notifyEnabled?: boolean;

		/**
		 * is_active
		 */
		status?: boolean;

		/**
		 * sort_order
		 */
		orderNum?: number;

		/**
		 * created_at
		 */
		createTime?: Date;

		/**
		 * updated_at
		 */
		updateTime?: Date;

		/**
		 * 任意键值
		 */
		[key: string]: any;
	}

	interface AiLog {
		/**
		 * id
		 */
		id?: number;

		/**
		 * provider_id
		 */
		providerId?: number;

		/**
		 * provider_name
		 */
		providerName?: string;

		/**
		 * model_id
		 */
		modelId?: number;

		/**
		 * model_name
		 */
		modelName?: string;

		/**
		 * profile_id
		 */
		profileId?: number;

		/**
		 * profile_name
		 */
		profileName?: string;

		/**
		 * user_id
		 */
		userId?: number;

		/**
		 * username
		 */
		username?: string;

		/**
		 * scenario
		 */
		scenario?: string;

		/**
		 * model_type
		 */
		modelType?: string;

		/**
		 * status
		 */
		status?: string;

		/**
		 * latency_ms
		 */
		latencyMs?: number;

		/**
		 * prompt_tokens
		 */
		promptTokens?: number;

		/**
		 * completion_tokens
		 */
		completionTokens?: number;

		/**
		 * total_tokens
		 */
		totalTokens?: number;

		/**
		 * cost_micro_usd
		 */
		costMicroUsd?: number;

		/**
		 * cost_usd
		 */
		costUsd?: number;

		/**
		 * currency
		 */
		currency?: string;

		/**
		 * error_message
		 */
		errorMessage?: string;

		/**
		 * request_id
		 */
		requestId?: string;

		/**
		 * request_options
		 */
		requestOptions?: string;

		/**
		 * created_at
		 */
		createTime?: Date;

		/**
		 * updated_at
		 */
		updateTime?: Date;

		/**
		 * 任意键值
		 */
		[key: string]: any;
	}

	interface model {
		/**
		 * id
		 */
		id?: number;

		/**
		 * provider_id
		 */
		providerId?: number;

		/**
		 * provider_name
		 */
		providerName?: string;

		/**
		 * code
		 */
		code?: string;

		/**
		 * name
		 */
		name?: string;

		/**
		 * model_type
		 */
		modelType?: string;

		/**
		 * capabilities
		 */
		capabilities?: string;

		/**
		 * context_window
		 */
		contextWindow?: number;

		/**
		 * max_output_tokens
		 */
		maxOutputTokens?: number;

		/**
		 * pricing_config
		 */
		pricingConfig?: string;

		/**
		 * default_config
		 */
		defaultConfig?: string;

		/**
		 * is_active
		 */
		status?: boolean;

		/**
		 * sort_order
		 */
		orderNum?: number;

		/**
		 * created_at
		 */
		createTime?: Date;

		/**
		 * updated_at
		 */
		updateTime?: Date;

		/**
		 * 任意键值
		 */
		[key: string]: any;
	}

	interface profile {
		/**
		 * id
		 */
		id?: number;

		/**
		 * code
		 */
		code?: string;

		/**
		 * name
		 */
		name?: string;

		/**
		 * model_id
		 */
		modelId?: number;

		/**
		 * model_name
		 */
		modelName?: string;

		/**
		 * model_type
		 */
		modelType?: string;

		/**
		 * model_code
		 */
		modelCode?: string;

		/**
		 * model_capabilities
		 */
		modelCapabilities?: string;

		/**
		 * provider_name
		 */
		providerName?: string;

		/**
		 * provider_code
		 */
		providerCode?: string;

		/**
		 * provider_adapter
		 */
		providerAdapter?: string;

		/**
		 * model_default_config
		 */
		modelDefaultConfig?: string;

		/**
		 * scenario
		 */
		scenario?: string;

		/**
		 * temperature
		 */
		temperature?: number;

		/**
		 * top_p
		 */
		topP?: number;

		/**
		 * max_tokens
		 */
		maxTokens?: number;

		/**
		 * response_format
		 */
		responseFormat?: string;

		/**
		 * tools_config
		 */
		toolsConfig?: string;

		/**
		 * timeout
		 */
		timeout?: number;

		/**
		 * retry_count
		 */
		retryCount?: number;

		/**
		 * retry_delay_seconds
		 */
		retryDelaySeconds?: number;

		/**
		 * fallback_profile_id
		 */
		fallbackProfileId?: number;

		/**
		 * is_default
		 */
		isDefault?: boolean;

		/**
		 * is_active
		 */
		status?: boolean;

		/**
		 * sort_order
		 */
		orderNum?: number;

		/**
		 * created_at
		 */
		createTime?: Date;

		/**
		 * updated_at
		 */
		updateTime?: Date;

		/**
		 * 任意键值
		 */
		[key: string]: any;
	}

	interface provider {
		/**
		 * id
		 */
		id?: number;

		/**
		 * code
		 */
		code?: string;

		/**
		 * name
		 */
		name?: string;

		/**
		 * adapter
		 */
		adapter?: string;

		/**
		 * base_url
		 */
		baseUrl?: string;

		/**
		 * api_key_mask
		 */
		apiKeyMask?: string;

		/**
		 * has_api_key
		 */
		hasApiKey?: boolean;

		/**
		 * admin_access_key_mask
		 */
		adminAccessKeyMask?: string;

		/**
		 * has_admin_access_key
		 */
		hasAdminAccessKey?: boolean;

		/**
		 * has_admin_secret_key
		 */
		hasAdminSecretKey?: boolean;

		/**
		 * extra_config
		 */
		extraConfig?: string;

		/**
		 * is_active
		 */
		status?: boolean;

		/**
		 * sort_order
		 */
		orderNum?: number;

		/**
		 * created_at
		 */
		createTime?: Date;

		/**
		 * updated_at
		 */
		updateTime?: Date;

		/**
		 * 任意键值
		 */
		[key: string]: any;
	}

	interface task {
		/**
		 * id
		 */
		id?: number;

		/**
		 * task_type
		 */
		taskType?: string;

		/**
		 * scenario
		 */
		scenario?: string;

		/**
		 * profile_code
		 */
		profileCode?: string;

		/**
		 * status
		 */
		status?: string;

		/**
		 * progress
		 */
		progress?: number;

		/**
		 * request_payload
		 */
		requestPayload?: string;

		/**
		 * result_payload
		 */
		resultPayload?: string;

		/**
		 * error_message
		 */
		errorMessage?: string;

		/**
		 * celery_task_id
		 */
		celeryTaskId?: string;

		/**
		 * created_by
		 */
		createdBy?: number;

		/**
		 * started_at
		 */
		startedAt?: Date;

		/**
		 * finished_at
		 */
		finishedAt?: Date;

		/**
		 * retry_count
		 */
		retryCount?: number;

		/**
		 * created_at
		 */
		createTime?: Date;

		/**
		 * updated_at
		 */
		updateTime?: Date;

		/**
		 * 任意键值
		 */
		[key: string]: any;
	}

	interface comm {
		/**
		 * 任意键值
		 */
		[key: string]: any;
	}

	interface health {
		/**
		 * 任意键值
		 */
		[key: string]: any;
	}

	interface open {
		/**
		 * 任意键值
		 */
		[key: string]: any;
	}

	interface session {
		/**
		 * 任意键值
		 */
		[key: string]: any;
	}

	interface department {
		/**
		 * id
		 */
		id?: number;

		/**
		 * parent_id
		 */
		parentId?: number;

		/**
		 * name
		 */
		name?: string;

		/**
		 * parent_name
		 */
		parentName?: string;

		/**
		 * sort_order
		 */
		orderNum?: number;

		/**
		 * is_active
		 */
		status?: boolean;

		/**
		 * created_at
		 */
		createTime?: Date;

		/**
		 * updated_at
		 */
		updateTime?: Date;

		/**
		 * 任意键值
		 */
		[key: string]: any;
	}

	interface log {
		/**
		 * id
		 */
		id?: number;

		/**
		 * user_id
		 */
		userId?: number;

		/**
		 * name
		 */
		name?: string;

		/**
		 * action
		 */
		action?: string;

		/**
		 * method
		 */
		method?: string;

		/**
		 * params
		 */
		params?: string;

		/**
		 * ip
		 */
		ip?: string;

		/**
		 * status
		 */
		status?: number;

		/**
		 * message
		 */
		message?: string;

		/**
		 * created_at
		 */
		createTime?: Date;

		/**
		 * 任意键值
		 */
		[key: string]: any;
	}

	interface login_log {
		/**
		 * id
		 */
		id?: number;

		/**
		 * user_id
		 */
		userId?: number;

		/**
		 * name
		 */
		name?: string;

		/**
		 * account
		 */
		account?: string;

		/**
		 * login_type
		 */
		loginType?: string;

		/**
		 * status
		 */
		status?: number;

		/**
		 * ip
		 */
		ip?: string;

		/**
		 * risk_hit
		 */
		riskHit?: number;

		/**
		 * reason
		 */
		reason?: string;

		/**
		 * client_type
		 */
		clientType?: string;

		/**
		 * device_id
		 */
		deviceId?: string;

		/**
		 * source_system
		 */
		sourceSystem?: string;

		/**
		 * user_agent
		 */
		userAgent?: string;

		/**
		 * created_at
		 */
		createTime?: Date;

		/**
		 * updated_at
		 */
		updateTime?: Date;

		/**
		 * 任意键值
		 */
		[key: string]: any;
	}

	interface menu {
		/**
		 * id
		 */
		id?: number;

		/**
		 * parent_id
		 */
		parentId?: number;

		/**
		 * parent_name
		 */
		parentName?: string;

		/**
		 * name
		 */
		name?: string;

		/**
		 * code
		 */
		code?: string;

		/**
		 * type
		 */
		type?: number;

		/**
		 * path
		 */
		router?: string;

		/**
		 * component
		 */
		viewPath?: string;

		/**
		 * icon
		 */
		icon?: string;

		/**
		 * keep_alive
		 */
		keepAlive?: boolean;

		/**
		 * is_show
		 */
		isShow?: boolean;

		/**
		 * permission
		 */
		perms?: string;

		/**
		 * sort_order
		 */
		orderNum?: number;

		/**
		 * is_active
		 */
		status?: boolean;

		/**
		 * created_at
		 */
		createTime?: Date;

		/**
		 * updated_at
		 */
		updateTime?: Date;

		/**
		 * 任意键值
		 */
		[key: string]: any;
	}

	interface param {
		/**
		 * id
		 */
		id?: number;

		/**
		 * name
		 */
		name?: string;

		/**
		 * key_name
		 */
		keyName?: string;

		/**
		 * data
		 */
		data?: string;

		/**
		 * data_type
		 */
		dataType?: number;

		/**
		 * remark
		 */
		remark?: string;

		/**
		 * created_at
		 */
		createTime?: Date;

		/**
		 * updated_at
		 */
		updateTime?: Date;

		/**
		 * 任意键值
		 */
		[key: string]: any;
	}

	interface role {
		/**
		 * id
		 */
		id?: number;

		/**
		 * name
		 */
		name?: string;

		/**
		 * label
		 */
		label?: string;

		/**
		 * code
		 */
		code?: string;

		/**
		 * remark
		 */
		remark?: string;

		/**
		 * is_active
		 */
		status?: boolean;

		/**
		 * relevance
		 */
		relevance?: number;

		/**
		 * menu_ids
		 */
		menuIdList?: number;

		/**
		 * department_ids
		 */
		departmentIdList?: number;

		/**
		 * created_at
		 */
		createTime?: Date;

		/**
		 * updated_at
		 */
		updateTime?: Date;

		/**
		 * 任意键值
		 */
		[key: string]: any;
	}

	interface security_log {
		/**
		 * id
		 */
		id?: number;

		/**
		 * operator_id
		 */
		operatorId?: number;

		/**
		 * operator_name
		 */
		operatorName?: string;

		/**
		 * operator_ip
		 */
		operatorIp?: string;

		/**
		 * target_type
		 */
		targetType?: string;

		/**
		 * target_id
		 */
		targetId?: number;

		/**
		 * target_name
		 */
		targetName?: string;

		/**
		 * operation
		 */
		operation?: string;

		/**
		 * module
		 */
		module?: string;

		/**
		 * resource_path
		 */
		resourcePath?: string;

		/**
		 * old_value
		 */
		oldValue?: string;

		/**
		 * new_value
		 */
		newValue?: string;

		/**
		 * diff_data
		 */
		diffData?: string;

		/**
		 * business_type
		 */
		businessType?: string;

		/**
		 * request_id
		 */
		requestId?: string;

		/**
		 * status
		 */
		status?: number;

		/**
		 * error_message
		 */
		errorMessage?: string;

		/**
		 * remark
		 */
		remark?: string;

		/**
		 * created_at
		 */
		createTime?: Date;

		/**
		 * updated_at
		 */
		updateTime?: Date;

		/**
		 * 任意键值
		 */
		[key: string]: any;
	}

	interface user {
		/**
		 * id
		 */
		id?: number;

		/**
		 * username
		 */
		username?: string;

		/**
		 * full_name
		 */
		name?: string;

		/**
		 * nick_name
		 */
		nickName?: string;

		/**
		 * head_img
		 */
		headImg?: string;

		/**
		 * email
		 */
		email?: string;

		/**
		 * phone
		 */
		phone?: string;

		/**
		 * remark
		 */
		remark?: string;

		/**
		 * department_id
		 */
		departmentId?: number;

		/**
		 * department_name
		 */
		departmentName?: string;

		/**
		 * role_ids
		 */
		roleIdList?: number;

		/**
		 * role_name
		 */
		roleName?: string;

		/**
		 * is_active
		 */
		status?: boolean;

		/**
		 * created_at
		 */
		createTime?: Date;

		/**
		 * updated_at
		 */
		updateTime?: Date;

		/**
		 * 任意键值
		 */
		[key: string]: any;
	}

	interface DictInfo {
		/**
		 * id
		 */
		id?: number;

		/**
		 * type_id
		 */
		typeId?: number;

		/**
		 * parent_id
		 */
		parentId?: number;

		/**
		 * name
		 */
		name?: string;

		/**
		 * value
		 */
		value?: string;

		/**
		 * sort_order
		 */
		orderNum?: number;

		/**
		 * remark
		 */
		remark?: string;

		/**
		 * created_at
		 */
		createTime?: Date;

		/**
		 * updated_at
		 */
		updateTime?: Date;

		/**
		 * 任意键值
		 */
		[key: string]: any;
	}

	interface DictType {
		/**
		 * id
		 */
		id?: number;

		/**
		 * name
		 */
		name?: string;

		/**
		 * key
		 */
		key?: string;

		/**
		 * created_at
		 */
		createTime?: Date;

		/**
		 * updated_at
		 */
		updateTime?: Date;

		/**
		 * 任意键值
		 */
		[key: string]: any;
	}

	interface asset {
		/**
		 * id
		 */
		id?: number;

		/**
		 * asset_type
		 */
		assetType?: string;

		/**
		 * source_type
		 */
		sourceType?: string;

		/**
		 * source_task_id
		 */
		sourceTaskId?: number;

		/**
		 * provider_code
		 */
		providerCode?: string;

		/**
		 * model_code
		 */
		modelCode?: string;

		/**
		 * profile_code
		 */
		profileCode?: string;

		/**
		 * original_url
		 */
		originalUrl?: string;

		/**
		 * storage_url
		 */
		storageUrl?: string;

		/**
		 * file_name
		 */
		fileName?: string;

		/**
		 * mime_type
		 */
		mimeType?: string;

		/**
		 * md5
		 */
		md5?: string;

		/**
		 * size_bytes
		 */
		sizeBytes?: number;

		/**
		 * width
		 */
		width?: number;

		/**
		 * height
		 */
		height?: number;

		/**
		 * duration_seconds
		 */
		durationSeconds?: number;

		/**
		 * prompt
		 */
		prompt?: string;

		/**
		 * params_payload
		 */
		paramsPayload?: string;

		/**
		 * status
		 */
		status?: string;

		/**
		 * error_message
		 */
		errorMessage?: string;

		/**
		 * created_by
		 */
		createdBy?: number;

		/**
		 * workflow_instance_id
		 */
		workflowInstanceId?: number;

		/**
		 * workflow_definition_id
		 */
		workflowDefinitionId?: number;

		/**
		 * workflow_node_id
		 */
		workflowNodeId?: string;

		/**
		 * created_at
		 */
		createTime?: Date;

		/**
		 * updated_at
		 */
		updateTime?: Date;

		/**
		 * 任意键值
		 */
		[key: string]: any;
	}

	interface message {
		/**
		 * id
		 */
		id?: number;

		/**
		 * title
		 */
		title?: string;

		/**
		 * content
		 */
		content?: string;

		/**
		 * message_type
		 */
		messageType?: string;

		/**
		 * level
		 */
		level?: string;

		/**
		 * source_module
		 */
		sourceModule?: string;

		/**
		 * business_key
		 */
		businessKey?: string;

		/**
		 * link_url
		 */
		linkUrl?: string;

		/**
		 * send_status
		 */
		sendStatus?: string;

		/**
		 * scheduled_at
		 */
		scheduledAt?: Date;

		/**
		 * expired_at
		 */
		expiredAt?: Date;

		/**
		 * sender_id
		 */
		senderId?: number;

		/**
		 * is_recalled
		 */
		isRecalled?: boolean;

		/**
		 * recalled_at
		 */
		recalledAt?: Date;

		/**
		 * recalled_by
		 */
		recalledBy?: number;

		/**
		 * created_at
		 */
		createTime?: Date;

		/**
		 * updated_at
		 */
		updateTime?: Date;

		/**
		 * 任意键值
		 */
		[key: string]: any;
	}

	interface rule {
		/**
		 * id
		 */
		id?: number;

		/**
		 * code
		 */
		code?: string;

		/**
		 * name
		 */
		name?: string;

		/**
		 * users
		 */
		users?: string;

		/**
		 * roles
		 */
		roles?: string;

		/**
		 * departments
		 */
		departments?: string;

		/**
		 * tenants
		 */
		tenants?: string;

		/**
		 * include_child_departments
		 */
		includeChildDepartments?: boolean;

		/**
		 * all_admins
		 */
		allAdmins?: boolean;

		/**
		 * condition
		 */
		condition?: string;

		/**
		 * is_active
		 */
		status?: boolean;

		/**
		 * created_at
		 */
		createTime?: Date;

		/**
		 * updated_at
		 */
		updateTime?: Date;

		/**
		 * 任意键值
		 */
		[key: string]: any;
	}

	interface template {
		/**
		 * id
		 */
		id?: number;

		/**
		 * code
		 */
		code?: string;

		/**
		 * name
		 */
		name?: string;

		/**
		 * title_template
		 */
		titleTemplate?: string;

		/**
		 * content_template
		 */
		contentTemplate?: string;

		/**
		 * default_level
		 */
		defaultLevel?: string;

		/**
		 * default_link_url
		 */
		defaultLinkUrl?: string;

		/**
		 * is_active
		 */
		status?: boolean;

		/**
		 * created_at
		 */
		createTime?: Date;

		/**
		 * updated_at
		 */
		updateTime?: Date;

		/**
		 * 任意键值
		 */
		[key: string]: any;
	}

	interface TaskInfo {
		/**
		 * id
		 */
		id?: number;

		/**
		 * job_id
		 */
		jobId?: string;

		/**
		 * name
		 */
		name?: string;

		/**
		 * cron
		 */
		cron?: string;

		/**
		 * every
		 */
		every?: number;

		/**
		 * remark
		 */
		remark?: string;

		/**
		 * status
		 */
		status?: number;

		/**
		 * start_date
		 */
		startDate?: Date;

		/**
		 * end_date
		 */
		endDate?: Date;

		/**
		 * data
		 */
		data?: string;

		/**
		 * service
		 */
		service?: string;

		/**
		 * type
		 */
		type?: number;

		/**
		 * next_run_time
		 */
		nextRunTime?: Date;

		/**
		 * task_type
		 */
		taskType?: number;

		/**
		 * last_execute_time
		 */
		lastExecuteTime?: Date;

		/**
		 * notify_enabled
		 */
		notifyEnabled?: boolean;

		/**
		 * notify_on_success
		 */
		notifyOnSuccess?: boolean;

		/**
		 * notify_on_failure
		 */
		notifyOnFailure?: boolean;

		/**
		 * notify_on_timeout
		 */
		notifyOnTimeout?: boolean;

		/**
		 * notify_recipients
		 */
		notifyRecipients?: string;

		/**
		 * notify_template_code
		 */
		notifyTemplateCode?: string;

		/**
		 * notify_timeout_ms
		 */
		notifyTimeoutMs?: number;

		/**
		 * created_at
		 */
		createTime?: Date;

		/**
		 * updated_at
		 */
		updateTime?: Date;

		/**
		 * 任意键值
		 */
		[key: string]: any;
	}

	interface artifact {
		/**
		 * id
		 */
		id?: number;

		/**
		 * instance_id
		 */
		instanceId?: number;

		/**
		 * definition_id
		 */
		definitionId?: number;

		/**
		 * version_id
		 */
		versionId?: number;

		/**
		 * run_type
		 */
		runType?: string;

		/**
		 * node_id
		 */
		nodeId?: string;

		/**
		 * user_id
		 */
		userId?: number;

		/**
		 * field_key
		 */
		fieldKey?: string;

		/**
		 * field_path
		 */
		fieldPath?: string;

		/**
		 * asset_type
		 */
		assetType?: string;

		/**
		 * media_asset_id
		 */
		mediaAssetId?: number;

		/**
		 * storage_url
		 */
		storageUrl?: string;

		/**
		 * original_url
		 */
		originalUrl?: string;

		/**
		 * content
		 */
		content?: string;

		/**
		 * content_ref
		 */
		contentRef?: string;

		/**
		 * created_at
		 */
		createTime?: Date;

		/**
		 * updated_at
		 */
		updateTime?: Date;

		/**
		 * 任意键值
		 */
		[key: string]: any;
	}

	interface definition {
		/**
		 * id
		 */
		id?: number;

		/**
		 * code
		 */
		code?: string;

		/**
		 * name
		 */
		name?: string;

		/**
		 * description
		 */
		description?: string;

		/**
		 * is_active
		 */
		status?: boolean;

		/**
		 * user_id
		 */
		userId?: number;

		/**
		 * current_version_id
		 */
		currentVersionId?: number;

		/**
		 * draft_version_id
		 */
		draftVersionId?: number;

		/**
		 * current_version_no
		 */
		currentVersionNo?: number;

		/**
		 * current_published_at
		 */
		currentPublishedAt?: Date;

		/**
		 * draft_graph_json
		 */
		draftGraphJson?: string;

		/**
		 * created_at
		 */
		createTime?: Date;

		/**
		 * updated_at
		 */
		updateTime?: Date;

		/**
		 * 任意键值
		 */
		[key: string]: any;
	}

	interface instance {
		/**
		 * id
		 */
		id?: number;

		/**
		 * definition_id
		 */
		definitionId?: number;

		/**
		 * definition_name
		 */
		definitionName?: string;

		/**
		 * version_id
		 */
		versionId?: number;

		/**
		 * version_no
		 */
		versionNo?: number;

		/**
		 * thread_id
		 */
		threadId?: string;

		/**
		 * status
		 */
		status?: string;

		/**
		 * current_node
		 */
		currentNode?: string;

		/**
		 * state_data
		 */
		stateData?: string;

		/**
		 * error_message
		 */
		errorMessage?: string;

		/**
		 * failed_node_id
		 */
		failedNodeId?: string;

		/**
		 * run_type
		 */
		runType?: string;

		/**
		 * eval_run_id
		 */
		evalRunId?: number;

		/**
		 * user_id
		 */
		userId?: number;

		/**
		 * created_at
		 */
		createTime?: Date;

		/**
		 * updated_at
		 */
		updateTime?: Date;

		/**
		 * total_tokens
		 */
		totalTokens?: number;

		/**
		 * cost_usd
		 */
		costUsd?: number;

		/**
		 * 任意键值
		 */
		[key: string]: any;
	}

	interface version {
		/**
		 * id
		 */
		id?: number;

		/**
		 * definition_id
		 */
		definitionId?: number;

		/**
		 * version_no
		 */
		versionNo?: number;

		/**
		 * status
		 */
		status?: string;

		/**
		 * change_note
		 */
		changeNote?: string;

		/**
		 * parent_version_id
		 */
		parentVersionId?: number;

		/**
		 * published_at
		 */
		publishedAt?: Date;

		/**
		 * published_by
		 */
		publishedBy?: number;

		/**
		 * created_at
		 */
		createTime?: Date;

		/**
		 * updated_at
		 */
		updateTime?: Date;

		/**
		 * 任意键值
		 */
		[key: string]: any;
	}

	interface annotation {
		/**
		 * id
		 */
		id?: number;

		/**
		 * case_result_id
		 */
		caseResultId?: number;

		/**
		 * annotator_user_id
		 */
		annotatorUserId?: number;

		/**
		 * label
		 */
		label?: string;

		/**
		 * score
		 */
		score?: number;

		/**
		 * reason
		 */
		reason?: string;

		/**
		 * is_gold
		 */
		isGold?: boolean;

		/**
		 * created_at
		 */
		createTime?: Date;

		/**
		 * updated_at
		 */
		updateTime?: Date;

		/**
		 * 任意键值
		 */
		[key: string]: any;
	}

	interface eval_run {
		/**
		 * id
		 */
		id?: number;

		/**
		 * test_set_id
		 */
		testSetId?: number;

		/**
		 * definition_id
		 */
		definitionId?: number;

		/**
		 * definition_version_id
		 */
		definitionVersionId?: number;

		/**
		 * version_label
		 */
		versionLabel?: string;

		/**
		 * status
		 */
		status?: string;

		/**
		 * total
		 */
		total?: number;

		/**
		 * passed
		 */
		passed?: number;

		/**
		 * failed
		 */
		failed?: number;

		/**
		 * errored
		 */
		errored?: number;

		/**
		 * avg_score
		 */
		avgScore?: number;

		/**
		 * pass_rate
		 */
		passRate?: number;

		/**
		 * p50_latency_ms
		 */
		p50LatencyMs?: number;

		/**
		 * p95_latency_ms
		 */
		p95LatencyMs?: number;

		/**
		 * p99_latency_ms
		 */
		p99LatencyMs?: number;

		/**
		 * max_latency_ms
		 */
		maxLatencyMs?: number;

		/**
		 * total_tokens
		 */
		totalTokens?: number;

		/**
		 * total_cost_micro_usd
		 */
		totalCostMicroUsd?: number;

		/**
		 * started_at
		 */
		startedAt?: Date;

		/**
		 * finished_at
		 */
		finishedAt?: Date;

		/**
		 * error_message
		 */
		errorMessage?: string;

		/**
		 * user_id
		 */
		userId?: number;

		/**
		 * created_at
		 */
		createTime?: Date;

		/**
		 * updated_at
		 */
		updateTime?: Date;

		/**
		 * 任意键值
		 */
		[key: string]: any;
	}

	interface test_case {
		/**
		 * id
		 */
		id?: number;

		/**
		 * test_set_id
		 */
		testSetId?: number;

		/**
		 * case_key
		 */
		caseKey?: string;

		/**
		 * input_data
		 */
		inputData?: string;

		/**
		 * expected_output
		 */
		expectedOutput?: string;

		/**
		 * expected_text
		 */
		expectedText?: string;

		/**
		 * evaluator_config
		 */
		evaluatorConfig?: string;

		/**
		 * weight
		 */
		weight?: number;

		/**
		 * sort_order
		 */
		orderNum?: number;

		/**
		 * tags
		 */
		tags?: string;

		/**
		 * 任意键值
		 */
		[key: string]: any;
	}

	interface test_set {
		/**
		 * id
		 */
		id?: number;

		/**
		 * name
		 */
		name?: string;

		/**
		 * description
		 */
		description?: string;

		/**
		 * definition_id
		 */
		definitionId?: number;

		/**
		 * items_count
		 */
		itemsCount?: number;

		/**
		 * tags
		 */
		tags?: string;

		/**
		 * user_id
		 */
		userId?: number;

		/**
		 * created_at
		 */
		createTime?: Date;

		/**
		 * updated_at
		 */
		updateTime?: Date;

		/**
		 * 任意键值
		 */
		[key: string]: any;
	}

	type json = any;

	type DictKey = string;

	interface PagePagination {
		size: number;
		page: number;
		total: number;
		[key: string]: any;
	}

	interface PageResponse<T> {
		pagination: PagePagination;
		list: T[];
		[key: string]: any;
	}

	interface AiGovernance_eventPageResponse {
		pagination: PagePagination;
		list: governance_event[];
	}

	interface AiGovernance_ruleAddResponse {
		/** id */ id: number;
		/** code */ code: string;
		/** name */ name: string;
		/** scopeType */ scopeType: string;
		/** userId */ userId?: number | null;
		/** username */ username?: string | null;
		/** profileId */ profileId?: number | null;
		/** profileName */ profileName?: string | null;
		/** period */ period: string;
		/** maxRequests */ maxRequests?: number | null;
		/** maxTokens */ maxTokens?: number | null;
		/** maxCostMicroUsd */ maxCostMicroUsd?: number | null;
		/** maxConcurrent */ maxConcurrent?: number | null;
		/** mode */ mode: string;
		/** notifyEnabled */ notifyEnabled: boolean;
		/** status */ status: boolean;
		/** orderNum */ orderNum?: number;
		/** createTime */ createTime: string;
		/** updateTime */ updateTime: string;
	}

	interface AiGovernance_rulePageResponse {
		pagination: PagePagination;
		list: governance_rule[];
	}

	interface AiGovernance_ruleUpdateResponse {
		/** id */ id: number;
		/** code */ code: string;
		/** name */ name: string;
		/** scopeType */ scopeType: string;
		/** userId */ userId?: number | null;
		/** username */ username?: string | null;
		/** profileId */ profileId?: number | null;
		/** profileName */ profileName?: string | null;
		/** period */ period: string;
		/** maxRequests */ maxRequests?: number | null;
		/** maxTokens */ maxTokens?: number | null;
		/** maxCostMicroUsd */ maxCostMicroUsd?: number | null;
		/** maxConcurrent */ maxConcurrent?: number | null;
		/** mode */ mode: string;
		/** notifyEnabled */ notifyEnabled: boolean;
		/** status */ status: boolean;
		/** orderNum */ orderNum?: number;
		/** createTime */ createTime: string;
		/** updateTime */ updateTime: string;
	}

	interface AiLogPageResponse {
		pagination: PagePagination;
		list: AiLog[];
	}

	interface AiModelAddResponse {
		/** id */ id: number;
		/** providerId */ providerId: number;
		/** providerName */ providerName?: string | null;
		/** code */ code: string;
		/** name */ name: string;
		/** modelType */ modelType: string;
		/** capabilities */ capabilities?: string | null;
		/** contextWindow */ contextWindow?: number | null;
		/** maxOutputTokens */ maxOutputTokens?: number | null;
		/** pricingConfig */ pricingConfig?: string | null;
		/** defaultConfig */ defaultConfig?: string | null;
		/** status */ status: boolean;
		/** orderNum */ orderNum?: number;
		/** createTime */ createTime: string;
		/** updateTime */ updateTime: string;
	}

	interface AiModelPageResponse {
		pagination: PagePagination;
		list: model[];
	}

	interface AiModelUpdateResponse {
		/** id */ id: number;
		/** providerId */ providerId: number;
		/** providerName */ providerName?: string | null;
		/** code */ code: string;
		/** name */ name: string;
		/** modelType */ modelType: string;
		/** capabilities */ capabilities?: string | null;
		/** contextWindow */ contextWindow?: number | null;
		/** maxOutputTokens */ maxOutputTokens?: number | null;
		/** pricingConfig */ pricingConfig?: string | null;
		/** defaultConfig */ defaultConfig?: string | null;
		/** status */ status: boolean;
		/** orderNum */ orderNum?: number;
		/** createTime */ createTime: string;
		/** updateTime */ updateTime: string;
	}

	interface AiProfileAddResponse {
		/** id */ id: number;
		/** code */ code: string;
		/** name */ name: string;
		/** modelId */ modelId: number;
		/** modelName */ modelName?: string | null;
		/** modelType */ modelType?: string | null;
		/** modelCode */ modelCode?: string | null;
		/** modelCapabilities */ modelCapabilities?: string | null;
		/** providerName */ providerName?: string | null;
		/** providerCode */ providerCode?: string | null;
		/** providerAdapter */ providerAdapter?: string | null;
		/** modelDefaultConfig */ modelDefaultConfig?: string | null;
		/** scenario */ scenario: string;
		/** temperature */ temperature?: number | null;
		/** topP */ topP?: number | null;
		/** maxTokens */ maxTokens?: number | null;
		/** responseFormat */ responseFormat?: string | null;
		/** toolsConfig */ toolsConfig?: string | null;
		/** timeout */ timeout?: number | null;
		/** retryCount */ retryCount?: number;
		/** retryDelaySeconds */ retryDelaySeconds?: number;
		/** fallbackProfileId */ fallbackProfileId?: number | null;
		/** isDefault */ isDefault: boolean;
		/** status */ status: boolean;
		/** orderNum */ orderNum?: number;
		/** createTime */ createTime: string;
		/** updateTime */ updateTime: string;
	}

	interface AiProfilePageResponse {
		pagination: PagePagination;
		list: profile[];
	}

	interface AiProfileUpdateResponse {
		/** id */ id: number;
		/** code */ code: string;
		/** name */ name: string;
		/** modelId */ modelId: number;
		/** modelName */ modelName?: string | null;
		/** modelType */ modelType?: string | null;
		/** modelCode */ modelCode?: string | null;
		/** modelCapabilities */ modelCapabilities?: string | null;
		/** providerName */ providerName?: string | null;
		/** providerCode */ providerCode?: string | null;
		/** providerAdapter */ providerAdapter?: string | null;
		/** modelDefaultConfig */ modelDefaultConfig?: string | null;
		/** scenario */ scenario: string;
		/** temperature */ temperature?: number | null;
		/** topP */ topP?: number | null;
		/** maxTokens */ maxTokens?: number | null;
		/** responseFormat */ responseFormat?: string | null;
		/** toolsConfig */ toolsConfig?: string | null;
		/** timeout */ timeout?: number | null;
		/** retryCount */ retryCount?: number;
		/** retryDelaySeconds */ retryDelaySeconds?: number;
		/** fallbackProfileId */ fallbackProfileId?: number | null;
		/** isDefault */ isDefault: boolean;
		/** status */ status: boolean;
		/** orderNum */ orderNum?: number;
		/** createTime */ createTime: string;
		/** updateTime */ updateTime: string;
	}

	interface AiProviderAddResponse {
		/** id */ id: number;
		/** code */ code: string;
		/** name */ name: string;
		/** adapter */ adapter: string;
		/** baseUrl */ baseUrl?: string | null;
		/** apiKeyMask */ apiKeyMask?: string | null;
		/** hasApiKey */ hasApiKey?: boolean;
		/** adminAccessKeyMask */ adminAccessKeyMask?: string | null;
		/** hasAdminAccessKey */ hasAdminAccessKey?: boolean;
		/** hasAdminSecretKey */ hasAdminSecretKey?: boolean;
		/** extraConfig */ extraConfig?: string | null;
		/** status */ status: boolean;
		/** orderNum */ orderNum?: number;
		/** createTime */ createTime: string;
		/** updateTime */ updateTime: string;
	}

	interface AiProviderPageResponse {
		pagination: PagePagination;
		list: provider[];
	}

	interface AiProviderUpdateResponse {
		/** id */ id: number;
		/** code */ code: string;
		/** name */ name: string;
		/** adapter */ adapter: string;
		/** baseUrl */ baseUrl?: string | null;
		/** apiKeyMask */ apiKeyMask?: string | null;
		/** hasApiKey */ hasApiKey?: boolean;
		/** adminAccessKeyMask */ adminAccessKeyMask?: string | null;
		/** hasAdminAccessKey */ hasAdminAccessKey?: boolean;
		/** hasAdminSecretKey */ hasAdminSecretKey?: boolean;
		/** extraConfig */ extraConfig?: string | null;
		/** status */ status: boolean;
		/** orderNum */ orderNum?: number;
		/** createTime */ createTime: string;
		/** updateTime */ updateTime: string;
	}

	interface AiTaskPageResponse {
		pagination: PagePagination;
		list: task[];
	}

	interface BaseCommPersonResponse {
		/** id */ id: number;
		/** createTime */ createTime: string;
		/** updateTime */ updateTime: string;
		/** departmentId */ departmentId?: number | null;
		/** name */ name: string;
		/** username */ username: string;
		/** passwordVersion */ passwordVersion?: number;
		/** nickName */ nickName?: string | null;
		/** headImg */ headImg?: string | null;
		/** phone */ phone?: string | null;
		/** email */ email?: string | null;
		/** remark */ remark?: string | null;
		/** status */ status?: number;
		/** isSuperAdmin */ isSuperAdmin?: number;
		/** isManager */ isManager?: number;
		/** isDepartmentLeader */ isDepartmentLeader?: number;
		/** orderNum */ orderNum?: number;
		/** openId */ openId?: string | null;
		/** unionId */ unionId?: string | null;
		/** socketId */ socketId?: string | null;
	}

	interface BaseOpenCaptchaResponse {
		/** captchaId */ captchaId: string;
		/** data */ data: any;
	}

	interface BaseOpenLoginResponse {
		/** token */ token: string;
		/** refreshToken */ refreshToken?: string | null;
		/** expire */ expire: number;
		/** refreshExpire */ refreshExpire: number;
		/** Loom 兼容用户信息 */ userInfo: {
			/** userId */ userId: number;
			/** username */ username: string;
			/** nickName */ nickName?: string | null;
			/** departmentId */ departmentId: number | null;
			/** roleCodes */ roleCodes: string[];
			/** perms */ perms: string[];
			/** isSuperAdmin */ isSuperAdmin: boolean;
			/** forcePasswordChange */ forcePasswordChange?: boolean;
		};
		/** perms */ perms: string[];
	}

	interface BaseOpenRefreshResponse {
		/** token */ token: string;
		/** refreshToken */ refreshToken?: string | null;
		/** expire */ expire: number;
		/** refreshExpire */ refreshExpire: number;
		/** Loom 兼容用户信息 */ userInfo: {
			/** userId */ userId: number;
			/** username */ username: string;
			/** nickName */ nickName?: string | null;
			/** departmentId */ departmentId: number | null;
			/** roleCodes */ roleCodes: string[];
			/** perms */ perms: string[];
			/** isSuperAdmin */ isSuperAdmin: boolean;
			/** forcePasswordChange */ forcePasswordChange?: boolean;
		};
		/** perms */ perms: string[];
	}

	interface BaseOpenRefreshTokenResponse {
		/** token */ token: string;
		/** refreshToken */ refreshToken?: string | null;
		/** expire */ expire: number;
		/** refreshExpire */ refreshExpire: number;
		/** Loom 兼容用户信息 */ userInfo: {
			/** userId */ userId: number;
			/** username */ username: string;
			/** nickName */ nickName?: string | null;
			/** departmentId */ departmentId: number | null;
			/** roleCodes */ roleCodes: string[];
			/** perms */ perms: string[];
			/** isSuperAdmin */ isSuperAdmin: boolean;
			/** forcePasswordChange */ forcePasswordChange?: boolean;
		};
		/** perms */ perms: string[];
	}

	interface BaseSysDepartmentAddResponse {
		/** id */ id: number;
		/** parentId */ parentId?: number | null;
		/** name */ name: string;
		/** parentName */ parentName?: string | null;
		/** orderNum */ orderNum: number;
		/** status */ status?: number;
		/** createTime */ createTime: string;
		/** updateTime */ updateTime: string;
	}

	interface BaseSysDepartmentPageResponse {
		pagination: PagePagination;
		list: department[];
	}

	interface BaseSysDepartmentUpdateResponse {
		/** id */ id: number;
		/** parentId */ parentId?: number | null;
		/** name */ name: string;
		/** parentName */ parentName?: string | null;
		/** orderNum */ orderNum: number;
		/** status */ status?: number;
		/** createTime */ createTime: string;
		/** updateTime */ updateTime: string;
	}

	interface BaseSysLogPageResponse {
		pagination: PagePagination;
		list: log[];
	}

	interface BaseSysLogin_logAddResponse {
		/** id */ id: number;
		/** userId */ userId?: number | null;
		/** name */ name?: string | null;
		/** account */ account?: string | null;
		/** loginType */ loginType: string;
		/** status */ status: number;
		/** ip */ ip?: string | null;
		/** riskHit */ riskHit?: number;
		/** reason */ reason?: string | null;
		/** clientType */ clientType?: string | null;
		/** deviceId */ deviceId?: string | null;
		/** sourceSystem */ sourceSystem?: string | null;
		/** userAgent */ userAgent?: string | null;
		/** createTime */ createTime: string;
		/** updateTime */ updateTime: string;
	}

	interface BaseSysLogin_logPageResponse {
		pagination: PagePagination;
		list: login_log[];
	}

	interface BaseSysLogin_logUpdateResponse {
		/** id */ id: number;
		/** userId */ userId?: number | null;
		/** name */ name?: string | null;
		/** account */ account?: string | null;
		/** loginType */ loginType: string;
		/** status */ status: number;
		/** ip */ ip?: string | null;
		/** riskHit */ riskHit?: number;
		/** reason */ reason?: string | null;
		/** clientType */ clientType?: string | null;
		/** deviceId */ deviceId?: string | null;
		/** sourceSystem */ sourceSystem?: string | null;
		/** userAgent */ userAgent?: string | null;
		/** createTime */ createTime: string;
		/** updateTime */ updateTime: string;
	}

	interface BaseSysMenuPageResponse {
		pagination: PagePagination;
		list: menu[];
	}

	interface BaseSysMenuParseResponse {
		/** list */ list?: {
			/** module */ module: string;
			/** resource */ resource: string;
			/** prefix */ prefix: string;
			/** controller */ controller: string;
			/** name */ name: string;
			/** router */ router: string;
			/** viewPath */ viewPath?: string | null;
			/** icon */ icon?: string | null;
			/** parentCode */ parentCode?: string | null;
			/** api */ api?: any[];
		}[];
	}

	interface BaseSysMenuUpdateResponse {
		/** id */ id: number;
		/** parentId */ parentId?: number | null;
		/** parentName */ parentName?: string | null;
		/** name */ name: string;
		/** code */ code: string;
		/** type */ type: number;
		/** router */ router?: string | null;
		/** viewPath */ viewPath?: string | null;
		/** icon */ icon?: string | null;
		/** keepAlive */ keepAlive?: boolean;
		/** isShow */ isShow?: boolean;
		/** perms */ perms?: string | null;
		/** orderNum */ orderNum: number;
		/** status */ status?: number;
		/** createTime */ createTime: string;
		/** updateTime */ updateTime: string;
	}

	interface BaseSysParamAddResponse {
		/** id */ id: number;
		/** name */ name: string;
		/** keyName */ keyName: string;
		/** data */ data?: string | null;
		/** dataType */ dataType?: number;
		/** remark */ remark?: string | null;
		/** createTime */ createTime: string;
		/** updateTime */ updateTime: string;
	}

	interface BaseSysParamPageResponse {
		pagination: PagePagination;
		list: param[];
	}

	interface BaseSysParamUpdateResponse {
		/** id */ id: number;
		/** name */ name: string;
		/** keyName */ keyName: string;
		/** data */ data?: string | null;
		/** dataType */ dataType?: number;
		/** remark */ remark?: string | null;
		/** createTime */ createTime: string;
		/** updateTime */ updateTime: string;
	}

	interface BaseSysRoleAddResponse {
		/** id */ id: number;
		/** name */ name: string;
		/** label */ label: string;
		/** code */ code: string;
		/** remark */ remark?: string | null;
		/** status */ status?: number;
		/** relevance */ relevance?: number;
		/** menuIdList */ menuIdList?: number[];
		/** departmentIdList */ departmentIdList?: number[];
		/** createTime */ createTime: string;
		/** updateTime */ updateTime: string;
	}

	interface BaseSysRolePageResponse {
		pagination: PagePagination;
		list: role[];
	}

	interface BaseSysRoleUpdateResponse {
		/** id */ id: number;
		/** name */ name: string;
		/** label */ label: string;
		/** code */ code: string;
		/** remark */ remark?: string | null;
		/** status */ status?: number;
		/** relevance */ relevance?: number;
		/** menuIdList */ menuIdList?: number[];
		/** departmentIdList */ departmentIdList?: number[];
		/** createTime */ createTime: string;
		/** updateTime */ updateTime: string;
	}

	interface BaseSysSecurity_logPageResponse {
		pagination: PagePagination;
		list: security_log[];
	}

	interface BaseSysUserAddResponse {
		/** id */ id: number;
		/** username */ username: string;
		/** name */ name: string;
		/** nickName */ nickName?: string | null;
		/** headImg */ headImg?: string | null;
		/** email */ email?: string | null;
		/** phone */ phone?: string | null;
		/** remark */ remark?: string | null;
		/** departmentId */ departmentId?: number | null;
		/** departmentName */ departmentName?: string | null;
		/** roleIdList */ roleIdList?: number[];
		/** roleName */ roleName?: string | null;
		/** status */ status?: number;
		/** createTime */ createTime: string;
		/** updateTime */ updateTime: string;
	}

	interface BaseSysUserAssignRolesResponse {
		/** id */ id: number;
		/** username */ username: string;
		/** name */ name: string;
		/** nickName */ nickName?: string | null;
		/** headImg */ headImg?: string | null;
		/** email */ email?: string | null;
		/** phone */ phone?: string | null;
		/** remark */ remark?: string | null;
		/** departmentId */ departmentId?: number | null;
		/** departmentName */ departmentName?: string | null;
		/** roleIdList */ roleIdList?: number[];
		/** roleName */ roleName?: string | null;
		/** status */ status?: number;
		/** createTime */ createTime: string;
		/** updateTime */ updateTime: string;
	}

	interface BaseSysUserMeResponse {
		/** userId */ userId: number;
		/** username */ username: string;
		/** nickName */ nickName?: string | null;
		/** departmentId */ departmentId: number | null;
		/** roleCodes */ roleCodes: string[];
		/** perms */ perms: string[];
		/** isSuperAdmin */ isSuperAdmin: boolean;
		/** forcePasswordChange */ forcePasswordChange?: boolean;
	}

	interface BaseSysUserPageResponse {
		pagination: PagePagination;
		list: user[];
	}

	interface BaseSysUserUpdateResponse {
		/** id */ id: number;
		/** username */ username: string;
		/** name */ name: string;
		/** nickName */ nickName?: string | null;
		/** headImg */ headImg?: string | null;
		/** email */ email?: string | null;
		/** phone */ phone?: string | null;
		/** remark */ remark?: string | null;
		/** departmentId */ departmentId?: number | null;
		/** departmentName */ departmentName?: string | null;
		/** roleIdList */ roleIdList?: number[];
		/** roleName */ roleName?: string | null;
		/** status */ status?: number;
		/** createTime */ createTime: string;
		/** updateTime */ updateTime: string;
	}

	interface DictInfoAddResponse {
		/** id */ id: number;
		/** typeId */ typeId: number;
		/** parentId */ parentId?: number | null;
		/** name */ name: string;
		/** value */ value?: string | null;
		/** orderNum */ orderNum?: number;
		/** remark */ remark?: string | null;
		/** createTime */ createTime: string;
		/** updateTime */ updateTime: string;
	}

	interface DictInfoPageResponse {
		pagination: PagePagination;
		list: DictInfo[];
	}

	interface DictInfoUpdateResponse {
		/** id */ id: number;
		/** typeId */ typeId: number;
		/** parentId */ parentId?: number | null;
		/** name */ name: string;
		/** value */ value?: string | null;
		/** orderNum */ orderNum?: number;
		/** remark */ remark?: string | null;
		/** createTime */ createTime: string;
		/** updateTime */ updateTime: string;
	}

	interface DictTypeAddResponse {
		/** id */ id: number;
		/** name */ name: string;
		/** key */ key: string;
		/** createTime */ createTime: string;
		/** updateTime */ updateTime: string;
	}

	interface DictTypePageResponse {
		pagination: PagePagination;
		list: DictType[];
	}

	interface DictTypeUpdateResponse {
		/** id */ id: number;
		/** name */ name: string;
		/** key */ key: string;
		/** createTime */ createTime: string;
		/** updateTime */ updateTime: string;
	}

	interface MediaAssetAddResponse {
		/** id */ id: number;
		/** assetType */ assetType: string;
		/** sourceType */ sourceType: string;
		/** sourceTaskId */ sourceTaskId?: number | null;
		/** providerCode */ providerCode?: string | null;
		/** modelCode */ modelCode?: string | null;
		/** profileCode */ profileCode?: string | null;
		/** originalUrl */ originalUrl?: string | null;
		/** storageUrl */ storageUrl?: string | null;
		/** fileName */ fileName?: string | null;
		/** mimeType */ mimeType?: string | null;
		/** md5 */ md5?: string | null;
		/** sizeBytes */ sizeBytes?: number;
		/** width */ width?: number | null;
		/** height */ height?: number | null;
		/** durationSeconds */ durationSeconds?: number | null;
		/** prompt */ prompt?: string | null;
		/** paramsPayload */ paramsPayload?: string | null;
		/** status */ status: string;
		/** errorMessage */ errorMessage?: string | null;
		/** createdBy */ createdBy?: number | null;
		/** workflowInstanceId */ workflowInstanceId?: number | null;
		/** workflowDefinitionId */ workflowDefinitionId?: number | null;
		/** workflowNodeId */ workflowNodeId?: string | null;
		/** createTime */ createTime: string;
		/** updateTime */ updateTime: string;
	}

	interface MediaAssetPageResponse {
		pagination: PagePagination;
		list: asset[];
	}

	interface MediaAssetUpdateResponse {
		/** id */ id: number;
		/** assetType */ assetType: string;
		/** sourceType */ sourceType: string;
		/** sourceTaskId */ sourceTaskId?: number | null;
		/** providerCode */ providerCode?: string | null;
		/** modelCode */ modelCode?: string | null;
		/** profileCode */ profileCode?: string | null;
		/** originalUrl */ originalUrl?: string | null;
		/** storageUrl */ storageUrl?: string | null;
		/** fileName */ fileName?: string | null;
		/** mimeType */ mimeType?: string | null;
		/** md5 */ md5?: string | null;
		/** sizeBytes */ sizeBytes?: number;
		/** width */ width?: number | null;
		/** height */ height?: number | null;
		/** durationSeconds */ durationSeconds?: number | null;
		/** prompt */ prompt?: string | null;
		/** paramsPayload */ paramsPayload?: string | null;
		/** status */ status: string;
		/** errorMessage */ errorMessage?: string | null;
		/** createdBy */ createdBy?: number | null;
		/** workflowInstanceId */ workflowInstanceId?: number | null;
		/** workflowDefinitionId */ workflowDefinitionId?: number | null;
		/** workflowNodeId */ workflowNodeId?: string | null;
		/** createTime */ createTime: string;
		/** updateTime */ updateTime: string;
	}

	interface NotificationMessageAddResponse {
		/** id */ id: number;
		/** title */ title: string;
		/** content */ content: string;
		/** messageType */ messageType: string;
		/** level */ level: string;
		/** sourceModule */ sourceModule?: string | null;
		/** businessKey */ businessKey?: string | null;
		/** linkUrl */ linkUrl?: string | null;
		/** sendStatus */ sendStatus: string;
		/** scheduledAt */ scheduledAt?: string | null;
		/** expiredAt */ expiredAt?: string | null;
		/** senderId */ senderId?: number | null;
		/** isRecalled */ isRecalled?: boolean;
		/** recalledAt */ recalledAt?: string | null;
		/** recalledBy */ recalledBy?: number | null;
		/** createTime */ createTime: string;
		/** updateTime */ updateTime: string;
	}

	interface NotificationMessagePageResponse {
		pagination: PagePagination;
		list: message[];
	}

	interface NotificationMessageUpdateResponse {
		/** id */ id: number;
		/** title */ title: string;
		/** content */ content: string;
		/** messageType */ messageType: string;
		/** level */ level: string;
		/** sourceModule */ sourceModule?: string | null;
		/** businessKey */ businessKey?: string | null;
		/** linkUrl */ linkUrl?: string | null;
		/** sendStatus */ sendStatus: string;
		/** scheduledAt */ scheduledAt?: string | null;
		/** expiredAt */ expiredAt?: string | null;
		/** senderId */ senderId?: number | null;
		/** isRecalled */ isRecalled?: boolean;
		/** recalledAt */ recalledAt?: string | null;
		/** recalledBy */ recalledBy?: number | null;
		/** createTime */ createTime: string;
		/** updateTime */ updateTime: string;
	}

	interface NotificationRuleAddResponse {
		/** id */ id: number;
		/** code */ code: string;
		/** name */ name: string;
		/** users */ users?: string | null;
		/** roles */ roles?: string | null;
		/** departments */ departments?: string | null;
		/** tenants */ tenants?: string | null;
		/** includeChildDepartments */ includeChildDepartments: boolean;
		/** allAdmins */ allAdmins: boolean;
		/** condition */ condition?: string | null;
		/** status */ status: boolean;
		/** createTime */ createTime: string;
		/** updateTime */ updateTime: string;
	}

	interface NotificationRulePageResponse {
		pagination: PagePagination;
		list: rule[];
	}

	interface NotificationRuleUpdateResponse {
		/** id */ id: number;
		/** code */ code: string;
		/** name */ name: string;
		/** users */ users?: string | null;
		/** roles */ roles?: string | null;
		/** departments */ departments?: string | null;
		/** tenants */ tenants?: string | null;
		/** includeChildDepartments */ includeChildDepartments: boolean;
		/** allAdmins */ allAdmins: boolean;
		/** condition */ condition?: string | null;
		/** status */ status: boolean;
		/** createTime */ createTime: string;
		/** updateTime */ updateTime: string;
	}

	interface NotificationTemplateAddResponse {
		/** id */ id: number;
		/** code */ code: string;
		/** name */ name: string;
		/** titleTemplate */ titleTemplate: string;
		/** contentTemplate */ contentTemplate: string;
		/** defaultLevel */ defaultLevel: string;
		/** defaultLinkUrl */ defaultLinkUrl?: string | null;
		/** status */ status: boolean;
		/** createTime */ createTime: string;
		/** updateTime */ updateTime: string;
	}

	interface NotificationTemplatePageResponse {
		pagination: PagePagination;
		list: template[];
	}

	interface NotificationTemplateUpdateResponse {
		/** id */ id: number;
		/** code */ code: string;
		/** name */ name: string;
		/** titleTemplate */ titleTemplate: string;
		/** contentTemplate */ contentTemplate: string;
		/** defaultLevel */ defaultLevel: string;
		/** defaultLinkUrl */ defaultLinkUrl?: string | null;
		/** status */ status: boolean;
		/** createTime */ createTime: string;
		/** updateTime */ updateTime: string;
	}

	interface TaskInfoAddResponse {
		/** id */ id: number;
		/** jobId */ jobId?: string | null;
		/** name */ name: string;
		/** cron */ cron?: string | null;
		/** every */ every?: number | null;
		/** remark */ remark?: string | null;
		/** status */ status: number;
		/** startDate */ startDate?: string | null;
		/** endDate */ endDate?: string | null;
		/** data */ data?: string | null;
		/** service */ service?: string | null;
		/** type */ type: number;
		/** nextRunTime */ nextRunTime?: string | null;
		/** taskType */ taskType: number;
		/** lastExecuteTime */ lastExecuteTime?: string | null;
		/** notifyEnabled */ notifyEnabled?: boolean;
		/** notifyOnSuccess */ notifyOnSuccess?: boolean;
		/** notifyOnFailure */ notifyOnFailure?: boolean;
		/** notifyOnTimeout */ notifyOnTimeout?: boolean;
		/** notifyRecipients */ notifyRecipients?: string | null;
		/** notifyTemplateCode */ notifyTemplateCode?: string | null;
		/** notifyTimeoutMs */ notifyTimeoutMs?: number;
		/** createTime */ createTime: string;
		/** updateTime */ updateTime: string;
	}

	interface TaskInfoPageResponse {
		pagination: PagePagination;
		list: TaskInfo[];
	}

	interface TaskInfoUpdateResponse {
		/** id */ id: number;
		/** jobId */ jobId?: string | null;
		/** name */ name: string;
		/** cron */ cron?: string | null;
		/** every */ every?: number | null;
		/** remark */ remark?: string | null;
		/** status */ status: number;
		/** startDate */ startDate?: string | null;
		/** endDate */ endDate?: string | null;
		/** data */ data?: string | null;
		/** service */ service?: string | null;
		/** type */ type: number;
		/** nextRunTime */ nextRunTime?: string | null;
		/** taskType */ taskType: number;
		/** lastExecuteTime */ lastExecuteTime?: string | null;
		/** notifyEnabled */ notifyEnabled?: boolean;
		/** notifyOnSuccess */ notifyOnSuccess?: boolean;
		/** notifyOnFailure */ notifyOnFailure?: boolean;
		/** notifyOnTimeout */ notifyOnTimeout?: boolean;
		/** notifyRecipients */ notifyRecipients?: string | null;
		/** notifyTemplateCode */ notifyTemplateCode?: string | null;
		/** notifyTimeoutMs */ notifyTimeoutMs?: number;
		/** createTime */ createTime: string;
		/** updateTime */ updateTime: string;
	}

	interface WorkflowArtifactPageResponse {
		pagination: PagePagination;
		list: artifact[];
	}

	interface WorkflowDefinitionAddResponse {
		/** id */ id: number;
		/** code */ code: string;
		/** name */ name: string;
		/** description */ description?: string | null;
		/** status */ status: number;
		/** userId */ userId?: number | null;
		/** currentVersionId */ currentVersionId?: number | null;
		/** draftVersionId */ draftVersionId?: number | null;
		/** currentVersionNo */ currentVersionNo?: number | null;
		/** currentPublishedAt */ currentPublishedAt?: string | null;
		/** draftGraphJson */ draftGraphJson?: string | null;
		/** createTime */ createTime: string;
		/** updateTime */ updateTime: string;
	}

	interface WorkflowDefinitionPageResponse {
		pagination: PagePagination;
		list: definition[];
	}

	interface WorkflowDefinitionUpdateResponse {
		/** id */ id: number;
		/** code */ code: string;
		/** name */ name: string;
		/** description */ description?: string | null;
		/** status */ status: number;
		/** userId */ userId?: number | null;
		/** currentVersionId */ currentVersionId?: number | null;
		/** draftVersionId */ draftVersionId?: number | null;
		/** currentVersionNo */ currentVersionNo?: number | null;
		/** currentPublishedAt */ currentPublishedAt?: string | null;
		/** draftGraphJson */ draftGraphJson?: string | null;
		/** createTime */ createTime: string;
		/** updateTime */ updateTime: string;
	}

	interface WorkflowInstancePageResponse {
		pagination: PagePagination;
		list: instance[];
	}

	interface WorkflowInstanceTestNodeResponse {
		/** output */ output: any;
		/** latencyMs */ latencyMs: number;
		/** error */ error?: string | null;
		/** isTimeout */ isTimeout?: boolean;
		/** instanceId */ instanceId?: number | null;
		/** hint */ hint?: string | null;
	}

	interface WorkflowVersionPageResponse {
		pagination: PagePagination;
		list: version[];
	}

	interface Workflow_annotationAnnotationAddResponse {
		/** id */ id: number;
		/** caseResultId */ caseResultId: number;
		/** annotatorUserId */ annotatorUserId?: number | null;
		/** label */ label: string;
		/** score */ score?: number | null;
		/** reason */ reason?: string | null;
		/** isGold */ isGold?: boolean;
		/** createTime */ createTime: string;
		/** updateTime */ updateTime: string;
	}

	interface Workflow_annotationAnnotationPageResponse {
		pagination: PagePagination;
		list: annotation[];
	}

	interface Workflow_annotationAnnotationUpdateResponse {
		/** id */ id: number;
		/** caseResultId */ caseResultId: number;
		/** annotatorUserId */ annotatorUserId?: number | null;
		/** label */ label: string;
		/** score */ score?: number | null;
		/** reason */ reason?: string | null;
		/** isGold */ isGold?: boolean;
		/** createTime */ createTime: string;
		/** updateTime */ updateTime: string;
	}

	interface Workflow_evalEval_runPageResponse {
		pagination: PagePagination;
		list: eval_run[];
	}

	interface Workflow_evalTest_caseAddResponse {
		/** id */ id: number;
		/** testSetId */ testSetId: number;
		/** caseKey */ caseKey: string;
		/** inputData */ inputData: string;
		/** expectedOutput */ expectedOutput?: string | null;
		/** expectedText */ expectedText?: string | null;
		/** evaluatorConfig */ evaluatorConfig?: string | null;
		/** weight */ weight?: number;
		/** orderNum */ orderNum?: number;
		/** tags */ tags?: string | null;
	}

	interface Workflow_evalTest_casePageResponse {
		pagination: PagePagination;
		list: test_case[];
	}

	interface Workflow_evalTest_caseUpdateResponse {
		/** id */ id: number;
		/** testSetId */ testSetId: number;
		/** caseKey */ caseKey: string;
		/** inputData */ inputData: string;
		/** expectedOutput */ expectedOutput?: string | null;
		/** expectedText */ expectedText?: string | null;
		/** evaluatorConfig */ evaluatorConfig?: string | null;
		/** weight */ weight?: number;
		/** orderNum */ orderNum?: number;
		/** tags */ tags?: string | null;
	}

	interface Workflow_evalTest_setAddResponse {
		/** id */ id: number;
		/** name */ name: string;
		/** description */ description?: string | null;
		/** definitionId */ definitionId?: number | null;
		/** itemsCount */ itemsCount?: number;
		/** tags */ tags?: string | null;
		/** userId */ userId?: number | null;
		/** createTime */ createTime: string;
		/** updateTime */ updateTime: string;
	}

	interface Workflow_evalTest_setPageResponse {
		pagination: PagePagination;
		list: test_set[];
	}

	interface Workflow_evalTest_setUpdateResponse {
		/** id */ id: number;
		/** name */ name: string;
		/** description */ description?: string | null;
		/** definitionId */ definitionId?: number | null;
		/** itemsCount */ itemsCount?: number;
		/** tags */ tags?: string | null;
		/** userId */ userId?: number | null;
		/** createTime */ createTime: string;
		/** updateTime */ updateTime: string;
	}

	interface AiDashboard {
		/**
		 * cost
		 */
		cost(data?: any): Promise<any>;

		/**
		 * 权限标识
		 */
		permission: { cost: string };

		/**
		 * 权限状态
		 */
		_permission: { cost: boolean };

		request: Request;
	}

	interface AiGovernance_event {
		/**
		 * info
		 */
		info(data: { id: number }): Promise<governance_event>;

		/**
		 * list
		 */
		list(data?: any): Promise<governance_event[]>;

		/**
		 * page
		 */
		page(data?: any): Promise<AiGovernance_eventPageResponse>;

		/**
		 * stats
		 */
		stats(data?: any): Promise<any>;

		/**
		 * 权限标识
		 */
		permission: { info: string; list: string; page: string; stats: string };

		/**
		 * 权限状态
		 */
		_permission: { info: boolean; list: boolean; page: boolean; stats: boolean };

		request: Request;
	}

	interface AiGovernance_rule {
		/**
		 * add
		 */
		add(data?: any): Promise<AiGovernance_ruleAddResponse>;

		/**
		 * delete
		 */
		delete(data?: any): Promise<any>;

		/**
		 * info
		 */
		info(data: { id: number }): Promise<governance_rule>;

		/**
		 * list
		 */
		list(data?: any): Promise<governance_rule[]>;

		/**
		 * match
		 */
		match(data?: any): Promise<any>;

		/**
		 * page
		 */
		page(data?: any): Promise<AiGovernance_rulePageResponse>;

		/**
		 * toggle
		 */
		toggle(data?: any): Promise<any>;

		/**
		 * update
		 */
		update(data?: any): Promise<AiGovernance_ruleUpdateResponse>;

		/**
		 * 权限标识
		 */
		permission: {
			add: string;
			delete: string;
			info: string;
			list: string;
			match: string;
			page: string;
			toggle: string;
			update: string;
		};

		/**
		 * 权限状态
		 */
		_permission: {
			add: boolean;
			delete: boolean;
			info: boolean;
			list: boolean;
			match: boolean;
			page: boolean;
			toggle: boolean;
			update: boolean;
		};

		request: Request;
	}

	interface AiLog {
		/**
		 * info
		 */
		info(data: { id: number }): Promise<AiLog>;

		/**
		 * list
		 */
		list(data?: any): Promise<AiLog[]>;

		/**
		 * page
		 */
		page(data?: any): Promise<AiLogPageResponse>;

		/**
		 * stats
		 */
		stats(data?: any): Promise<any>;

		/**
		 * 权限标识
		 */
		permission: { info: string; list: string; page: string; stats: string };

		/**
		 * 权限状态
		 */
		_permission: { info: boolean; list: boolean; page: boolean; stats: boolean };

		request: Request;
	}

	interface AiModel {
		/**
		 * add
		 */
		add(data?: any): Promise<AiModelAddResponse>;

		/**
		 * delete
		 */
		delete(data?: any): Promise<any>;

		/**
		 * info
		 */
		info(data: { id: number }): Promise<model>;

		/**
		 * list
		 */
		list(data?: any): Promise<model[]>;

		/**
		 * page
		 */
		page(data?: any): Promise<AiModelPageResponse>;

		/**
		 * update
		 */
		update(data?: any): Promise<AiModelUpdateResponse>;

		/**
		 * 权限标识
		 */
		permission: {
			add: string;
			delete: string;
			info: string;
			list: string;
			page: string;
			update: string;
		};

		/**
		 * 权限状态
		 */
		_permission: {
			add: boolean;
			delete: boolean;
			info: boolean;
			list: boolean;
			page: boolean;
			update: boolean;
		};

		request: Request;
	}

	interface AiProfile {
		/**
		 * add
		 */
		add(data?: any): Promise<AiProfileAddResponse>;

		/**
		 * delete
		 */
		delete(data?: any): Promise<any>;

		/**
		 * info
		 */
		info(data: { id: number }): Promise<profile>;

		/**
		 * list
		 */
		list(data?: any): Promise<profile[]>;

		/**
		 * page
		 */
		page(data?: any): Promise<AiProfilePageResponse>;

		/**
		 * setDefault
		 */
		setDefault(data?: any): Promise<any>;

		/**
		 * test
		 */
		test(data?: any): Promise<any>;

		/**
		 * update
		 */
		update(data?: any): Promise<AiProfileUpdateResponse>;

		/**
		 * 权限标识
		 */
		permission: {
			add: string;
			delete: string;
			info: string;
			list: string;
			page: string;
			setDefault: string;
			test: string;
			update: string;
		};

		/**
		 * 权限状态
		 */
		_permission: {
			add: boolean;
			delete: boolean;
			info: boolean;
			list: boolean;
			page: boolean;
			setDefault: boolean;
			test: boolean;
			update: boolean;
		};

		request: Request;
	}

	interface AiProvider {
		/**
		 * add
		 */
		add(data?: any): Promise<AiProviderAddResponse>;

		/**
		 * catalog
		 */
		catalog(data?: any): Promise<any>;

		/**
		 * delete
		 */
		delete(data?: any): Promise<any>;

		/**
		 * importCatalog
		 */
		importCatalog(data?: any): Promise<any>;

		/**
		 * info
		 */
		info(data: { id: number }): Promise<provider>;

		/**
		 * list
		 */
		list(data?: any): Promise<provider[]>;

		/**
		 * page
		 */
		page(data?: any): Promise<AiProviderPageResponse>;

		/**
		 * syncModels
		 */
		syncModels(data?: any): Promise<any>;

		/**
		 * test
		 */
		test(data?: any): Promise<any>;

		/**
		 * update
		 */
		update(data?: any): Promise<AiProviderUpdateResponse>;

		/**
		 * 权限标识
		 */
		permission: {
			add: string;
			catalog: string;
			delete: string;
			importCatalog: string;
			info: string;
			list: string;
			page: string;
			syncModels: string;
			test: string;
			update: string;
		};

		/**
		 * 权限状态
		 */
		_permission: {
			add: boolean;
			catalog: boolean;
			delete: boolean;
			importCatalog: boolean;
			info: boolean;
			list: boolean;
			page: boolean;
			syncModels: boolean;
			test: boolean;
			update: boolean;
		};

		request: Request;
	}

	interface AiTask {
		/**
		 * cancel
		 */
		cancel(data?: any): Promise<any>;

		/**
		 * info
		 */
		info(data: { id: number }): Promise<task>;

		/**
		 * list
		 */
		list(data?: any): Promise<task[]>;

		/**
		 * page
		 */
		page(data?: any): Promise<AiTaskPageResponse>;

		/**
		 * retry
		 */
		retry(data?: any): Promise<any>;

		/**
		 * stats
		 */
		stats(data?: any): Promise<any>;

		/**
		 * submit
		 */
		submit(data?: any): Promise<any>;

		/**
		 * 权限标识
		 */
		permission: {
			cancel: string;
			info: string;
			list: string;
			page: string;
			retry: string;
			stats: string;
			submit: string;
		};

		/**
		 * 权限状态
		 */
		_permission: {
			cancel: boolean;
			info: boolean;
			list: boolean;
			page: boolean;
			retry: boolean;
			stats: boolean;
			submit: boolean;
		};

		request: Request;
	}

	interface BaseComm {
		/**
		 * logout
		 */
		logout(data?: any): Promise<any>;

		/**
		 * permmenu
		 */
		permmenu(data?: any): Promise<any>;

		/**
		 * person
		 */
		person(data?: any): Promise<BaseCommPersonResponse>;

		/**
		 * personUpdate
		 */
		personUpdate(data?: any): Promise<any>;

		/**
		 * program
		 */
		program(data?: any): Promise<string>;

		/**
		 * upload
		 */
		upload(data?: any): Promise<any>;

		/**
		 * uploadMode
		 */
		uploadMode(data?: any): Promise<any>;

		/**
		 * 权限标识
		 */
		permission: {
			logout: string;
			permmenu: string;
			person: string;
			personUpdate: string;
			program: string;
			upload: string;
			uploadMode: string;
		};

		/**
		 * 权限状态
		 */
		_permission: {
			logout: boolean;
			permmenu: boolean;
			person: boolean;
			personUpdate: boolean;
			program: boolean;
			upload: boolean;
			uploadMode: boolean;
		};

		request: Request;
	}

	interface BaseHealth {
		/**
		 * ping
		 */
		ping(data?: any): Promise<any>;

		/**
		 * 权限标识
		 */
		permission: { ping: string };

		/**
		 * 权限状态
		 */
		_permission: { ping: boolean };

		request: Request;
	}

	interface BaseOpen {
		/**
		 * captcha
		 */
		captcha(data?: {
			width?: number;
			height?: number;
			color?: string;
		}): Promise<BaseOpenCaptchaResponse>;

		/**
		 * config
		 */
		config(data?: any): Promise<any>;

		/**
		 * eps
		 */
		eps(data?: any): Promise<any>;

		/**
		 * login
		 */
		login(data?: any): Promise<BaseOpenLoginResponse>;

		/**
		 * logout
		 */
		logout(data?: any): Promise<any>;

		/**
		 * refresh
		 */
		refresh(data?: any): Promise<BaseOpenRefreshResponse>;

		/**
		 * refreshToken
		 */
		refreshToken(data?: any): Promise<BaseOpenRefreshTokenResponse>;

		/**
		 * revoke
		 */
		revoke(data?: any): Promise<any>;

		/**
		 * 权限标识
		 */
		permission: {
			captcha: string;
			config: string;
			eps: string;
			login: string;
			logout: string;
			refresh: string;
			refreshToken: string;
			revoke: string;
		};

		/**
		 * 权限状态
		 */
		_permission: {
			captcha: boolean;
			config: boolean;
			eps: boolean;
			login: boolean;
			logout: boolean;
			refresh: boolean;
			refreshToken: boolean;
			revoke: boolean;
		};

		request: Request;
	}

	interface BaseSession {
		/**
		 * list
		 */
		list(data?: any): Promise<session[]>;

		/**
		 * revoke
		 */
		revoke(data?: any): Promise<any>;

		/**
		 * 权限标识
		 */
		permission: { list: string; revoke: string };

		/**
		 * 权限状态
		 */
		_permission: { list: boolean; revoke: boolean };

		request: Request;
	}

	interface BaseSysDepartment {
		/**
		 * add
		 */
		add(data?: any): Promise<BaseSysDepartmentAddResponse>;

		/**
		 * delete
		 */
		delete(data?: any): Promise<any>;

		/**
		 * info
		 */
		info(data: { id: number }): Promise<department>;

		/**
		 * list
		 */
		list(data?: any): Promise<department[]>;

		/**
		 * order
		 */
		order(data?: any): Promise<any>;

		/**
		 * page
		 */
		page(data?: any): Promise<BaseSysDepartmentPageResponse>;

		/**
		 * update
		 */
		update(data?: any): Promise<BaseSysDepartmentUpdateResponse>;

		/**
		 * 权限标识
		 */
		permission: {
			add: string;
			delete: string;
			info: string;
			list: string;
			order: string;
			page: string;
			update: string;
		};

		/**
		 * 权限状态
		 */
		_permission: {
			add: boolean;
			delete: boolean;
			info: boolean;
			list: boolean;
			order: boolean;
			page: boolean;
			update: boolean;
		};

		request: Request;
	}

	interface BaseSysLog {
		/**
		 * clear
		 */
		clear(data?: any): Promise<any>;

		/**
		 * getKeep
		 */
		getKeep(data?: any): Promise<string>;

		/**
		 * page
		 */
		page(data?: any): Promise<BaseSysLogPageResponse>;

		/**
		 * setKeep
		 */
		setKeep(data?: any): Promise<any>;

		/**
		 * 权限标识
		 */
		permission: { clear: string; getKeep: string; page: string; setKeep: string };

		/**
		 * 权限状态
		 */
		_permission: { clear: boolean; getKeep: boolean; page: boolean; setKeep: boolean };

		request: Request;
	}

	interface BaseSysLogin_log {
		/**
		 * add
		 */
		add(data?: any): Promise<BaseSysLogin_logAddResponse>;

		/**
		 * delete
		 */
		delete(data?: any): Promise<any>;

		/**
		 * info
		 */
		info(data: { id: number }): Promise<login_log>;

		/**
		 * list
		 */
		list(data?: any): Promise<login_log[]>;

		/**
		 * page
		 */
		page(data?: any): Promise<BaseSysLogin_logPageResponse>;

		/**
		 * update
		 */
		update(data?: any): Promise<BaseSysLogin_logUpdateResponse>;

		/**
		 * 权限标识
		 */
		permission: {
			add: string;
			delete: string;
			info: string;
			list: string;
			page: string;
			update: string;
		};

		/**
		 * 权限状态
		 */
		_permission: {
			add: boolean;
			delete: boolean;
			info: boolean;
			list: boolean;
			page: boolean;
			update: boolean;
		};

		request: Request;
	}

	interface BaseSysMenu {
		/**
		 * add
		 */
		add(
			data?: any
		): Promise<
			| {
					/** id */ id: number;
					/** parentId */ parentId?: number | null;
					/** parentName */ parentName?: string | null;
					/** name */ name: string;
					/** code */ code: string;
					/** type */ type: number;
					/** router */ router?: string | null;
					/** viewPath */ viewPath?: string | null;
					/** icon */ icon?: string | null;
					/** keepAlive */ keepAlive?: boolean;
					/** isShow */ isShow?: boolean;
					/** perms */ perms?: string | null;
					/** orderNum */ orderNum: number;
					/** status */ status?: number;
					/** createTime */ createTime: string;
					/** updateTime */ updateTime: string;
			  }
			| {
					/** id */ id: number;
					/** parentId */ parentId?: number | null;
					/** parentName */ parentName?: string | null;
					/** name */ name: string;
					/** code */ code: string;
					/** type */ type: number;
					/** router */ router?: string | null;
					/** viewPath */ viewPath?: string | null;
					/** icon */ icon?: string | null;
					/** keepAlive */ keepAlive?: boolean;
					/** isShow */ isShow?: boolean;
					/** perms */ perms?: string | null;
					/** orderNum */ orderNum: number;
					/** status */ status?: number;
					/** createTime */ createTime: string;
					/** updateTime */ updateTime: string;
			  }[]
		>;

		/**
		 * create
		 */
		create(
			data?: any
		): Promise<
			{
				/** id */ id: number;
				/** parentId */ parentId?: number | null;
				/** parentName */ parentName?: string | null;
				/** name */ name: string;
				/** code */ code: string;
				/** type */ type: number;
				/** router */ router?: string | null;
				/** viewPath */ viewPath?: string | null;
				/** icon */ icon?: string | null;
				/** keepAlive */ keepAlive?: boolean;
				/** isShow */ isShow?: boolean;
				/** perms */ perms?: string | null;
				/** orderNum */ orderNum: number;
				/** status */ status?: number;
				/** createTime */ createTime: string;
				/** updateTime */ updateTime: string;
			}[]
		>;

		/**
		 * currentTree
		 */
		currentTree(
			data?: any
		): Promise<
			{
				/** id */ id: number;
				/** parentId */ parentId?: number | null;
				/** parentName */ parentName?: string | null;
				/** name */ name: string;
				/** code */ code: string;
				/** type */ type: number;
				/** router */ router?: string | null;
				/** viewPath */ viewPath?: string | null;
				/** icon */ icon?: string | null;
				/** keepAlive */ keepAlive?: boolean;
				/** isShow */ isShow?: boolean;
				/** perms */ perms?: string | null;
				/** orderNum */ orderNum: number;
				/** status */ status?: number;
				/** createTime */ createTime: string;
				/** updateTime */ updateTime: string;
				/** children */ children?: any[];
			}[]
		>;

		/**
		 * delete
		 */
		delete(data?: any): Promise<any>;

		/**
		 * export
		 */
		export(data?: any): Promise<any[]>;

		/**
		 * import
		 */
		import(data?: any): Promise<any>;

		/**
		 * info
		 */
		info(data: { id: number }): Promise<menu>;

		/**
		 * list
		 */
		list(data?: any): Promise<menu[]>;

		/**
		 * page
		 */
		page(data?: any): Promise<BaseSysMenuPageResponse>;

		/**
		 * parse
		 */
		parse(data?: any): Promise<BaseSysMenuParseResponse>;

		/**
		 * roleMenuIds
		 */
		roleMenuIds(data: { role_id: number }): Promise<number[]>;

		/**
		 * tree
		 */
		tree(
			data?: any
		): Promise<
			{
				/** id */ id: number;
				/** parentId */ parentId?: number | null;
				/** parentName */ parentName?: string | null;
				/** name */ name: string;
				/** code */ code: string;
				/** type */ type: number;
				/** router */ router?: string | null;
				/** viewPath */ viewPath?: string | null;
				/** icon */ icon?: string | null;
				/** keepAlive */ keepAlive?: boolean;
				/** isShow */ isShow?: boolean;
				/** perms */ perms?: string | null;
				/** orderNum */ orderNum: number;
				/** status */ status?: number;
				/** createTime */ createTime: string;
				/** updateTime */ updateTime: string;
				/** children */ children?: any[];
			}[]
		>;

		/**
		 * update
		 */
		update(data?: any): Promise<BaseSysMenuUpdateResponse>;

		/**
		 * 权限标识
		 */
		permission: {
			add: string;
			create: string;
			currentTree: string;
			delete: string;
			export: string;
			import: string;
			info: string;
			list: string;
			page: string;
			parse: string;
			roleMenuIds: string;
			tree: string;
			update: string;
		};

		/**
		 * 权限状态
		 */
		_permission: {
			add: boolean;
			create: boolean;
			currentTree: boolean;
			delete: boolean;
			export: boolean;
			import: boolean;
			info: boolean;
			list: boolean;
			page: boolean;
			parse: boolean;
			roleMenuIds: boolean;
			tree: boolean;
			update: boolean;
		};

		request: Request;
	}

	interface BaseSysParam {
		/**
		 * add
		 */
		add(data?: any): Promise<BaseSysParamAddResponse>;

		/**
		 * delete
		 */
		delete(data?: any): Promise<any>;

		/**
		 * html
		 */
		html(data: { key: string }): Promise<string>;

		/**
		 * info
		 */
		info(data: { id: number }): Promise<param>;

		/**
		 * page
		 */
		page(data?: any): Promise<BaseSysParamPageResponse>;

		/**
		 * update
		 */
		update(data?: any): Promise<BaseSysParamUpdateResponse>;

		/**
		 * 权限标识
		 */
		permission: {
			add: string;
			delete: string;
			html: string;
			info: string;
			page: string;
			update: string;
		};

		/**
		 * 权限状态
		 */
		_permission: {
			add: boolean;
			delete: boolean;
			html: boolean;
			info: boolean;
			page: boolean;
			update: boolean;
		};

		request: Request;
	}

	interface BaseSysRole {
		/**
		 * add
		 */
		add(data?: any): Promise<BaseSysRoleAddResponse>;

		/**
		 * assignMenus
		 */
		assignMenus(data?: any): Promise<any>;

		/**
		 * delete
		 */
		delete(data?: any): Promise<any>;

		/**
		 * info
		 */
		info(data: { id: number }): Promise<role>;

		/**
		 * list
		 */
		list(data?: any): Promise<role[]>;

		/**
		 * page
		 */
		page(data?: any): Promise<BaseSysRolePageResponse>;

		/**
		 * update
		 */
		update(data?: any): Promise<BaseSysRoleUpdateResponse>;

		/**
		 * 权限标识
		 */
		permission: {
			add: string;
			assignMenus: string;
			delete: string;
			info: string;
			list: string;
			page: string;
			update: string;
		};

		/**
		 * 权限状态
		 */
		_permission: {
			add: boolean;
			assignMenus: boolean;
			delete: boolean;
			info: boolean;
			list: boolean;
			page: boolean;
			update: boolean;
		};

		request: Request;
	}

	interface BaseSysSecurity_log {
		/**
		 * info
		 */
		info(data: { id: number }): Promise<security_log>;

		/**
		 * list
		 */
		list(data?: any): Promise<security_log[]>;

		/**
		 * page
		 */
		page(data?: any): Promise<BaseSysSecurity_logPageResponse>;

		/**
		 * 权限标识
		 */
		permission: { info: string; list: string; page: string };

		/**
		 * 权限状态
		 */
		_permission: { info: boolean; list: boolean; page: boolean };

		request: Request;
	}

	interface BaseSysUser {
		/**
		 * add
		 */
		add(data?: any): Promise<BaseSysUserAddResponse>;

		/**
		 * assignRoles
		 */
		assignRoles(data?: any): Promise<BaseSysUserAssignRolesResponse>;

		/**
		 * delete
		 */
		delete(data?: any): Promise<any>;

		/**
		 * info
		 */
		info(data: { id: number }): Promise<user>;

		/**
		 * list
		 */
		list(data?: any): Promise<user[]>;

		/**
		 * me
		 */
		me(data?: any): Promise<BaseSysUserMeResponse>;

		/**
		 * move
		 */
		move(data?: any): Promise<any>;

		/**
		 * page
		 */
		page(data?: any): Promise<BaseSysUserPageResponse>;

		/**
		 * update
		 */
		update(data?: any): Promise<BaseSysUserUpdateResponse>;

		/**
		 * 权限标识
		 */
		permission: {
			add: string;
			assignRoles: string;
			delete: string;
			info: string;
			list: string;
			me: string;
			move: string;
			page: string;
			update: string;
		};

		/**
		 * 权限状态
		 */
		_permission: {
			add: boolean;
			assignRoles: boolean;
			delete: boolean;
			info: boolean;
			list: boolean;
			me: boolean;
			move: boolean;
			page: boolean;
			update: boolean;
		};

		request: Request;
	}

	interface DictInfo {
		/**
		 * add
		 */
		add(data?: any): Promise<DictInfoAddResponse>;

		/**
		 * data
		 */
		data(data?: any): Promise<any>;

		/**
		 * delete
		 */
		delete(data?: any): Promise<any>;

		/**
		 * info
		 */
		info(data: { id: number }): Promise<DictInfo>;

		/**
		 * list
		 */
		list(data?: any): Promise<DictInfo[]>;

		/**
		 * page
		 */
		page(data?: any): Promise<DictInfoPageResponse>;

		/**
		 * types
		 */
		types(data?: any): Promise<any[]>;

		/**
		 * update
		 */
		update(data?: any): Promise<DictInfoUpdateResponse>;

		/**
		 * 权限标识
		 */
		permission: {
			add: string;
			data: string;
			delete: string;
			info: string;
			list: string;
			page: string;
			types: string;
			update: string;
		};

		/**
		 * 权限状态
		 */
		_permission: {
			add: boolean;
			data: boolean;
			delete: boolean;
			info: boolean;
			list: boolean;
			page: boolean;
			types: boolean;
			update: boolean;
		};

		request: Request;
	}

	interface DictType {
		/**
		 * add
		 */
		add(data?: any): Promise<DictTypeAddResponse>;

		/**
		 * delete
		 */
		delete(data?: any): Promise<any>;

		/**
		 * info
		 */
		info(data: { id: number }): Promise<DictType>;

		/**
		 * list
		 */
		list(data?: any): Promise<DictType[]>;

		/**
		 * page
		 */
		page(data?: any): Promise<DictTypePageResponse>;

		/**
		 * update
		 */
		update(data?: any): Promise<DictTypeUpdateResponse>;

		/**
		 * 权限标识
		 */
		permission: {
			add: string;
			delete: string;
			info: string;
			list: string;
			page: string;
			update: string;
		};

		/**
		 * 权限状态
		 */
		_permission: {
			add: boolean;
			delete: boolean;
			info: boolean;
			list: boolean;
			page: boolean;
			update: boolean;
		};

		request: Request;
	}

	interface MediaAsset {
		/**
		 * add
		 */
		add(data?: any): Promise<MediaAssetAddResponse>;

		/**
		 * delete
		 */
		delete(data?: any): Promise<any>;

		/**
		 * downloadToken
		 */
		downloadToken(data?: any): Promise<any>;

		/**
		 * info
		 */
		info(data: { id: number }): Promise<asset>;

		/**
		 * list
		 */
		list(data?: any): Promise<asset[]>;

		/**
		 * page
		 */
		page(data?: any): Promise<MediaAssetPageResponse>;

		/**
		 * proxyImage
		 */
		proxyImage(data: { url: string }): Promise<any>;

		/**
		 * retry
		 */
		retry(data?: any): Promise<any>;

		/**
		 * retryFailed
		 */
		retryFailed(data?: any): Promise<any>;

		/**
		 * stats
		 */
		stats(data?: any): Promise<any>;

		/**
		 * update
		 */
		update(data?: any): Promise<MediaAssetUpdateResponse>;

		/**
		 * upload
		 */
		upload(data?: any): Promise<any>;

		/**
		 * 权限标识
		 */
		permission: {
			add: string;
			delete: string;
			downloadToken: string;
			info: string;
			list: string;
			page: string;
			proxyImage: string;
			retry: string;
			retryFailed: string;
			stats: string;
			update: string;
			upload: string;
		};

		/**
		 * 权限状态
		 */
		_permission: {
			add: boolean;
			delete: boolean;
			downloadToken: boolean;
			info: boolean;
			list: boolean;
			page: boolean;
			proxyImage: boolean;
			retry: boolean;
			retryFailed: boolean;
			stats: boolean;
			update: boolean;
			upload: boolean;
		};

		request: Request;
	}

	interface NotificationMessage {
		/**
		 * add
		 */
		add(data?: any): Promise<NotificationMessageAddResponse>;

		/**
		 * archive
		 */
		archive(data?: any): Promise<any>;

		/**
		 * delete
		 */
		delete(data?: any): Promise<any>;

		/**
		 * info
		 */
		info(data: { id: number }): Promise<message>;

		/**
		 * list
		 */
		list(data?: any): Promise<message[]>;

		/**
		 * mine
		 */
		mine(data?: {
			includeArchived?: boolean;
			messageType?: string;
			readStatus?: string;
			limit?: number;
			offset?: number;
		}): Promise<any>;

		/**
		 * myInfo
		 */
		myInfo(data: { id: number }): Promise<any>;

		/**
		 * page
		 */
		page(data?: any): Promise<NotificationMessagePageResponse>;

		/**
		 * previewRecipients
		 */
		previewRecipients(data?: any): Promise<any>;

		/**
		 * read
		 */
		read(data?: any): Promise<any>;

		/**
		 * readAll
		 */
		readAll(data?: any): Promise<any>;

		/**
		 * recall
		 */
		recall(data?: any): Promise<any>;

		/**
		 * recipients
		 */
		recipients(data: { id: number }): Promise<any>;

		/**
		 * send
		 */
		send(data?: any): Promise<any>;

		/**
		 * stats
		 */
		stats(data?: any): Promise<any>;

		/**
		 * unarchive
		 */
		unarchive(data?: any): Promise<any>;

		/**
		 * unreadCount
		 */
		unreadCount(data?: any): Promise<any>;

		/**
		 * update
		 */
		update(data?: any): Promise<NotificationMessageUpdateResponse>;

		/**
		 * 权限标识
		 */
		permission: {
			add: string;
			archive: string;
			delete: string;
			info: string;
			list: string;
			mine: string;
			myInfo: string;
			page: string;
			previewRecipients: string;
			read: string;
			readAll: string;
			recall: string;
			recipients: string;
			send: string;
			stats: string;
			unarchive: string;
			unreadCount: string;
			update: string;
		};

		/**
		 * 权限状态
		 */
		_permission: {
			add: boolean;
			archive: boolean;
			delete: boolean;
			info: boolean;
			list: boolean;
			mine: boolean;
			myInfo: boolean;
			page: boolean;
			previewRecipients: boolean;
			read: boolean;
			readAll: boolean;
			recall: boolean;
			recipients: boolean;
			send: boolean;
			stats: boolean;
			unarchive: boolean;
			unreadCount: boolean;
			update: boolean;
		};

		request: Request;
	}

	interface NotificationRule {
		/**
		 * add
		 */
		add(data?: any): Promise<NotificationRuleAddResponse>;

		/**
		 * delete
		 */
		delete(data?: any): Promise<any>;

		/**
		 * info
		 */
		info(data: { id: number }): Promise<rule>;

		/**
		 * list
		 */
		list(data?: any): Promise<rule[]>;

		/**
		 * page
		 */
		page(data?: any): Promise<NotificationRulePageResponse>;

		/**
		 * update
		 */
		update(data?: any): Promise<NotificationRuleUpdateResponse>;

		/**
		 * 权限标识
		 */
		permission: {
			add: string;
			delete: string;
			info: string;
			list: string;
			page: string;
			update: string;
		};

		/**
		 * 权限状态
		 */
		_permission: {
			add: boolean;
			delete: boolean;
			info: boolean;
			list: boolean;
			page: boolean;
			update: boolean;
		};

		request: Request;
	}

	interface NotificationTemplate {
		/**
		 * add
		 */
		add(data?: any): Promise<NotificationTemplateAddResponse>;

		/**
		 * delete
		 */
		delete(data?: any): Promise<any>;

		/**
		 * info
		 */
		info(data: { id: number }): Promise<template>;

		/**
		 * list
		 */
		list(data?: any): Promise<template[]>;

		/**
		 * page
		 */
		page(data?: any): Promise<NotificationTemplatePageResponse>;

		/**
		 * preview
		 */
		preview(data?: any): Promise<any>;

		/**
		 * update
		 */
		update(data?: any): Promise<NotificationTemplateUpdateResponse>;

		/**
		 * 权限标识
		 */
		permission: {
			add: string;
			delete: string;
			info: string;
			list: string;
			page: string;
			preview: string;
			update: string;
		};

		/**
		 * 权限状态
		 */
		_permission: {
			add: boolean;
			delete: boolean;
			info: boolean;
			list: boolean;
			page: boolean;
			preview: boolean;
			update: boolean;
		};

		request: Request;
	}

	interface TaskInfo {
		/**
		 * add
		 */
		add(data?: any): Promise<TaskInfoAddResponse>;

		/**
		 * delete
		 */
		delete(data?: any): Promise<any>;

		/**
		 * info
		 */
		info(data: { id: number }): Promise<TaskInfo>;

		/**
		 * list
		 */
		list(data?: any): Promise<TaskInfo[]>;

		/**
		 * log
		 */
		log(data?: any): Promise<any>;

		/**
		 * once
		 */
		once(data?: any): Promise<any>;

		/**
		 * page
		 */
		page(data?: any): Promise<TaskInfoPageResponse>;

		/**
		 * start
		 */
		start(data?: any): Promise<any>;

		/**
		 * stop
		 */
		stop(data?: any): Promise<any>;

		/**
		 * update
		 */
		update(data?: any): Promise<TaskInfoUpdateResponse>;

		/**
		 * 权限标识
		 */
		permission: {
			add: string;
			delete: string;
			info: string;
			list: string;
			log: string;
			once: string;
			page: string;
			start: string;
			stop: string;
			update: string;
		};

		/**
		 * 权限状态
		 */
		_permission: {
			add: boolean;
			delete: boolean;
			info: boolean;
			list: boolean;
			log: boolean;
			once: boolean;
			page: boolean;
			start: boolean;
			stop: boolean;
			update: boolean;
		};

		request: Request;
	}

	interface WorkflowArtifact {
		/**
		 * delete
		 */
		delete(data?: any): Promise<any>;

		/**
		 * info
		 */
		info(data: { id: number }): Promise<artifact>;

		/**
		 * page
		 */
		page(data?: any): Promise<WorkflowArtifactPageResponse>;

		/**
		 * 权限标识
		 */
		permission: { delete: string; info: string; page: string };

		/**
		 * 权限状态
		 */
		_permission: { delete: boolean; info: boolean; page: boolean };

		request: Request;
	}

	interface WorkflowDefinition {
		/**
		 * add
		 */
		add(data?: any): Promise<WorkflowDefinitionAddResponse>;

		/**
		 * delete
		 */
		delete(data?: any): Promise<any>;

		/**
		 * info
		 */
		info(data: { id: number }): Promise<definition>;

		/**
		 * list
		 */
		list(data?: any): Promise<definition[]>;

		/**
		 * page
		 */
		page(data?: any): Promise<WorkflowDefinitionPageResponse>;

		/**
		 * saveDraft
		 */
		saveDraft(data?: any): Promise<any>;

		/**
		 * update
		 */
		update(data?: any): Promise<WorkflowDefinitionUpdateResponse>;

		/**
		 * 权限标识
		 */
		permission: {
			add: string;
			delete: string;
			info: string;
			list: string;
			page: string;
			saveDraft: string;
			update: string;
		};

		/**
		 * 权限状态
		 */
		_permission: {
			add: boolean;
			delete: boolean;
			info: boolean;
			list: boolean;
			page: boolean;
			saveDraft: boolean;
			update: boolean;
		};

		request: Request;
	}

	interface WorkflowInstance {
		/**
		 * cancel
		 */
		cancel(data?: any): Promise<any>;

		/**
		 * delete
		 */
		delete(data?: any): Promise<any>;

		/**
		 * info
		 */
		info(data: { id: number }): Promise<instance>;

		/**
		 * list
		 */
		list(data?: any): Promise<instance[]>;

		/**
		 * logs
		 */
		logs(data: {
			instanceId: number;
			/** 仅返回 id 大于此值的日志（增量拉取）  */
			sinceLogId?: string;
			/** 最多返回条数，缺省全量  */
			limit?: string;
		}): Promise<
			{
				/** id */ id: number;
				/** instanceId */ instanceId: number;
				/** nodeId */ nodeId: string;
				/** nodeName */ nodeName: string;
				/** nodeType */ nodeType: string;
				/** inputData */ inputData: string;
				/** outputData */ outputData: string;
				/** latencyMs */ latencyMs: number;
				/** status */ status: string;
				/** errorMessage */ errorMessage?: string | null;
				/** createTime */ createTime: string;
			}[]
		>;

		/**
		 * page
		 */
		page(data?: any): Promise<WorkflowInstancePageResponse>;

		/**
		 * resume
		 */
		resume(data?: any): Promise<any>;

		/**
		 * start
		 */
		start(data?: any): Promise<any>;

		/**
		 * stream
		 */
		stream(data: { instanceId: number }): Promise<any>;

		/**
		 * testNode
		 */
		testNode(data?: any): Promise<WorkflowInstanceTestNodeResponse>;

		/**
		 * trial
		 */
		trial(data?: any): Promise<any>;

		/**
		 * 权限标识
		 */
		permission: {
			cancel: string;
			delete: string;
			info: string;
			list: string;
			logs: string;
			page: string;
			resume: string;
			start: string;
			stream: string;
			testNode: string;
			trial: string;
		};

		/**
		 * 权限状态
		 */
		_permission: {
			cancel: boolean;
			delete: boolean;
			info: boolean;
			list: boolean;
			logs: boolean;
			page: boolean;
			resume: boolean;
			start: boolean;
			stream: boolean;
			testNode: boolean;
			trial: boolean;
		};

		request: Request;
	}

	interface WorkflowVersion {
		/**
		 * diff
		 */
		diff(data: { versionA: number; versionB: number }): Promise<any>;

		/**
		 * info
		 */
		info(data: { id: number }): Promise<version>;

		/**
		 * list
		 */
		list(data?: any): Promise<version[]>;

		/**
		 * page
		 */
		page(data?: any): Promise<WorkflowVersionPageResponse>;

		/**
		 * publish
		 */
		publish(data?: any): Promise<any>;

		/**
		 * rollback
		 */
		rollback(data?: any): Promise<any>;

		/**
		 * 权限标识
		 */
		permission: {
			diff: string;
			info: string;
			list: string;
			page: string;
			publish: string;
			rollback: string;
		};

		/**
		 * 权限状态
		 */
		_permission: {
			diff: boolean;
			info: boolean;
			list: boolean;
			page: boolean;
			publish: boolean;
			rollback: boolean;
		};

		request: Request;
	}

	interface Workflow_annotationAnnotation {
		/**
		 * add
		 */
		add(data?: any): Promise<Workflow_annotationAnnotationAddResponse>;

		/**
		 * delete
		 */
		delete(data?: any): Promise<any>;

		/**
		 * info
		 */
		info(data: { id: number }): Promise<annotation>;

		/**
		 * kappa
		 */
		kappa(data?: any): Promise<any>;

		/**
		 * list
		 */
		list(data?: any): Promise<annotation[]>;

		/**
		 * page
		 */
		page(data?: any): Promise<Workflow_annotationAnnotationPageResponse>;

		/**
		 * update
		 */
		update(data?: any): Promise<Workflow_annotationAnnotationUpdateResponse>;

		/**
		 * 权限标识
		 */
		permission: {
			add: string;
			delete: string;
			info: string;
			kappa: string;
			list: string;
			page: string;
			update: string;
		};

		/**
		 * 权限状态
		 */
		_permission: {
			add: boolean;
			delete: boolean;
			info: boolean;
			kappa: boolean;
			list: boolean;
			page: boolean;
			update: boolean;
		};

		request: Request;
	}

	interface Workflow_evalEval_run {
		/**
		 * cancel
		 */
		cancel(data?: any): Promise<any>;

		/**
		 * cases
		 */
		cases(data: { evalRunId: number; page?: number; size?: number }): Promise<any>;

		/**
		 * compare
		 */
		compare(data: { runA: number; runB: number }): Promise<any>;

		/**
		 * delete
		 */
		delete(data?: any): Promise<any>;

		/**
		 * info
		 */
		info(data: { id: number }): Promise<eval_run>;

		/**
		 * list
		 */
		list(data?: any): Promise<eval_run[]>;

		/**
		 * page
		 */
		page(data?: any): Promise<Workflow_evalEval_runPageResponse>;

		/**
		 * poll
		 */
		poll(data: {
			evalRunId: number;
			/** 最长等待秒数  */
			timeout?: number;
			/** 轮询间隔秒数  */
			interval?: number;
		}): Promise<any>;

		/**
		 * sampleProduction
		 */
		sampleProduction(data?: any): Promise<any>;

		/**
		 * start
		 */
		start(data?: any): Promise<any>;

		/**
		 * 权限标识
		 */
		permission: {
			cancel: string;
			cases: string;
			compare: string;
			delete: string;
			info: string;
			list: string;
			page: string;
			poll: string;
			sampleProduction: string;
			start: string;
		};

		/**
		 * 权限状态
		 */
		_permission: {
			cancel: boolean;
			cases: boolean;
			compare: boolean;
			delete: boolean;
			info: boolean;
			list: boolean;
			page: boolean;
			poll: boolean;
			sampleProduction: boolean;
			start: boolean;
		};

		request: Request;
	}

	interface Workflow_evalTest_case {
		/**
		 * add
		 */
		add(data?: any): Promise<Workflow_evalTest_caseAddResponse>;

		/**
		 * delete
		 */
		delete(data?: any): Promise<any>;

		/**
		 * info
		 */
		info(data: { id: number }): Promise<test_case>;

		/**
		 * list
		 */
		list(data?: any): Promise<test_case[]>;

		/**
		 * page
		 */
		page(data?: any): Promise<Workflow_evalTest_casePageResponse>;

		/**
		 * update
		 */
		update(data?: any): Promise<Workflow_evalTest_caseUpdateResponse>;

		/**
		 * 权限标识
		 */
		permission: {
			add: string;
			delete: string;
			info: string;
			list: string;
			page: string;
			update: string;
		};

		/**
		 * 权限状态
		 */
		_permission: {
			add: boolean;
			delete: boolean;
			info: boolean;
			list: boolean;
			page: boolean;
			update: boolean;
		};

		request: Request;
	}

	interface Workflow_evalTest_set {
		/**
		 * add
		 */
		add(data?: any): Promise<Workflow_evalTest_setAddResponse>;

		/**
		 * delete
		 */
		delete(data?: any): Promise<any>;

		/**
		 * importCases
		 */
		importCases(data?: any): Promise<any>;

		/**
		 * info
		 */
		info(data: { id: number }): Promise<test_set>;

		/**
		 * list
		 */
		list(data?: any): Promise<test_set[]>;

		/**
		 * page
		 */
		page(data?: any): Promise<Workflow_evalTest_setPageResponse>;

		/**
		 * update
		 */
		update(data?: any): Promise<Workflow_evalTest_setUpdateResponse>;

		/**
		 * 权限标识
		 */
		permission: {
			add: string;
			delete: string;
			importCases: string;
			info: string;
			list: string;
			page: string;
			update: string;
		};

		/**
		 * 权限状态
		 */
		_permission: {
			add: boolean;
			delete: boolean;
			importCases: boolean;
			info: boolean;
			list: boolean;
			page: boolean;
			update: boolean;
		};

		request: Request;
	}

	interface RequestOptions {
		url: string;
		method?: "OPTIONS" | "GET" | "HEAD" | "POST" | "PUT" | "DELETE" | "TRACE" | "CONNECT";
		data?: any;
		params?: any;
		headers?: any;
		timeout?: number;
		[key: string]: any;
	}

	type Request = (options: RequestOptions) => Promise<any>;

	type Service = {
		request: Request;

		ai: {
			dashboard: AiDashboard;
			governance_event: AiGovernance_event;
			governance_rule: AiGovernance_rule;
			log: AiLog;
			model: AiModel;
			profile: AiProfile;
			provider: AiProvider;
			task: AiTask;
		};
		base: {
			comm: BaseComm;
			health: BaseHealth;
			open: BaseOpen;
			session: BaseSession;
			sys: {
				department: BaseSysDepartment;
				log: BaseSysLog;
				login_log: BaseSysLogin_log;
				menu: BaseSysMenu;
				param: BaseSysParam;
				role: BaseSysRole;
				security_log: BaseSysSecurity_log;
				user: BaseSysUser;
			};
		};
		dict: { info: DictInfo; type: DictType };
		media: { asset: MediaAsset };
		notification: {
			message: NotificationMessage;
			rule: NotificationRule;
			template: NotificationTemplate;
		};
		task: { info: TaskInfo };
		workflow: {
			artifact: WorkflowArtifact;
			definition: WorkflowDefinition;
			instance: WorkflowInstance;
			version: WorkflowVersion;
		};
		workflow_annotation: { annotation: Workflow_annotationAnnotation };
		workflow_eval: {
			eval_run: Workflow_evalEval_run;
			test_case: Workflow_evalTest_case;
			test_set: Workflow_evalTest_set;
		};
	};
}
