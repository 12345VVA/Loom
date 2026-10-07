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
		 * custom_config
		 */
		customConfig?: string;

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
		 * memory_write_enabled
		 */
		memoryWriteEnabled?: boolean;

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

	type DictKey = "ai_model_capability" | "status";

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
		/** customConfig */ customConfig?: string | null;
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
		/** customConfig */ customConfig?: string | null;
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
		/** memoryWriteEnabled */ memoryWriteEnabled?: boolean;
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
		/** memoryWriteEnabled */ memoryWriteEnabled?: boolean;
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
		 * AI 成本看板统计
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
		 * 获取详情
		 */
		info(data: { id: number }): Promise<governance_event>;

		/**
		 * 获取列表
		 */
		list(data?: any): Promise<governance_event[]>;

		/**
		 * 获取分页
		 */
		page(data?: any): Promise<AiGovernance_eventPageResponse>;

		/**
		 * AI 治理事件统计
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
		 * 新增
		 */
		add(data?: any): Promise<AiGovernance_ruleAddResponse>;

		/**
		 * 删除
		 */
		delete(data?: any): Promise<any>;

		/**
		 * 获取详情
		 */
		info(data: { id: number }): Promise<governance_rule>;

		/**
		 * 获取列表
		 */
		list(data?: any): Promise<governance_rule[]>;

		/**
		 * 测试 AI 治理规则匹配
		 */
		match(data?: any): Promise<any>;

		/**
		 * 获取分页
		 */
		page(data?: any): Promise<AiGovernance_rulePageResponse>;

		/**
		 * 启停 AI 治理规则
		 */
		toggle(data?: any): Promise<any>;

		/**
		 * 更新
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
		 * 获取详情
		 */
		info(data: { id: number }): Promise<AiLog>;

		/**
		 * 获取列表
		 */
		list(data?: any): Promise<AiLog[]>;

		/**
		 * 获取分页
		 */
		page(data?: any): Promise<AiLogPageResponse>;

		/**
		 * AI 调用日志统计
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
		 * 新增
		 */
		add(data?: any): Promise<AiModelAddResponse>;

		/**
		 * 删除
		 */
		delete(data?: any): Promise<any>;

		/**
		 * 获取详情
		 */
		info(data: { id: number }): Promise<model>;

		/**
		 * 获取列表
		 */
		list(data?: any): Promise<model[]>;

		/**
		 * 获取分页
		 */
		page(data?: any): Promise<AiModelPageResponse>;

		/**
		 * 更新
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
		 * 新增
		 */
		add(data?: any): Promise<AiProfileAddResponse>;

		/**
		 * 删除
		 */
		delete(data?: any): Promise<any>;

		/**
		 * 获取详情
		 */
		info(data: { id: number }): Promise<profile>;

		/**
		 * 获取列表
		 */
		list(data?: any): Promise<profile[]>;

		/**
		 * 获取分页
		 */
		page(data?: any): Promise<AiProfilePageResponse>;

		/**
		 * 设为默认调用配置
		 */
		setDefault(data?: any): Promise<any>;

		/**
		 * 测试模型调用配置
		 */
		test(data?: any): Promise<any>;

		/**
		 * 更新
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
		 * 新增
		 */
		add(data?: any): Promise<AiProviderAddResponse>;

		/**
		 * 获取模型厂商预设清单
		 */
		catalog(data?: any): Promise<any>;

		/**
		 * 删除
		 */
		delete(data?: any): Promise<any>;

		/**
		 * 导入模型厂商预设
		 */
		importCatalog(data?: any): Promise<any>;

		/**
		 * 获取详情
		 */
		info(data: { id: number }): Promise<provider>;

		/**
		 * 获取列表
		 */
		list(data?: any): Promise<provider[]>;

		/**
		 * 获取分页
		 */
		page(data?: any): Promise<AiProviderPageResponse>;

		/**
		 * 同步厂商模型列表
		 */
		syncModels(data?: any): Promise<any>;

		/**
		 * 测试模型厂商连接
		 */
		test(data?: any): Promise<any>;

		/**
		 * 更新
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
		 * 取消 AI 生成任务
		 */
		cancel(data?: any): Promise<any>;

		/**
		 * 获取详情
		 */
		info(data: { id: number }): Promise<task>;

		/**
		 * 获取列表
		 */
		list(data?: any): Promise<task[]>;

		/**
		 * 获取分页
		 */
		page(data?: any): Promise<AiTaskPageResponse>;

		/**
		 * 重试 AI 生成任务
		 */
		retry(data?: any): Promise<any>;

		/**
		 * AI 生成任务统计
		 */
		stats(data?: any): Promise<any>;

		/**
		 * 提交 AI 生成任务
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
		 * 退出登录
		 */
		logout(data?: any): Promise<any>;

		/**
		 * 获取权限与菜单
		 */
		permmenu(data?: any): Promise<any>;

		/**
		 * 获取当前用户个人信息
		 */
		person(data?: any): Promise<BaseCommPersonResponse>;

		/**
		 * 修改当前用户信息
		 */
		personUpdate(data?: any): Promise<any>;

		/**
		 * 编程语言
		 */
		program(data?: any): Promise<string>;

		/**
		 * 文件上传
		 */
		upload(data?: any): Promise<any>;

		/**
		 * 文件上传模式
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
		 * 健康检查接口
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
		 * 验证码
		 */
		captcha(data?: {
			width?: number;
			height?: number;
			color?: string;
		}): Promise<BaseOpenCaptchaResponse>;

		/**
		 * 登录页公开配置
		 */
		config(data?: any): Promise<any>;

		/**
		 * 导出 EPS 扫描元数据
		 */
		eps(data?: any): Promise<any>;

		/**
		 * 账号密码登录
		 */
		login(data?: any): Promise<BaseOpenLoginResponse>;

		/**
		 * 退出登录并清理服务端登录态
		 */
		logout(data?: any): Promise<any>;

		/**
		 * 刷新访问令牌
		 */
		refresh(data?: any): Promise<BaseOpenRefreshResponse>;

		/**
		 * 刷新访问令牌
		 */
		refreshToken(data?: any): Promise<BaseOpenRefreshTokenResponse>;

		/**
		 * 登出清理（仅凭 refresh cookie，无需有效 access token）
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
		 * 当前用户设备列表
		 */
		list(data?: any): Promise<session[]>;

		/**
		 * 踢出指定设备
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
		 * 新增
		 */
		add(data?: any): Promise<BaseSysDepartmentAddResponse>;

		/**
		 * 删除
		 */
		delete(data?: any): Promise<any>;

		/**
		 * 获取详情
		 */
		info(data: { id: number }): Promise<department>;

		/**
		 * 获取列表
		 */
		list(data?: any): Promise<department[]>;

		/**
		 * 部门排序
		 */
		order(data?: any): Promise<any>;

		/**
		 * 获取分页
		 */
		page(data?: any): Promise<BaseSysDepartmentPageResponse>;

		/**
		 * 更新
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
		 * 清理
		 */
		clear(data?: any): Promise<any>;

		/**
		 * 获得日志保存时间
		 */
		getKeep(data?: any): Promise<string>;

		/**
		 * 获取分页
		 */
		page(data?: any): Promise<BaseSysLogPageResponse>;

		/**
		 * 日志保存时间
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
		 * 新增
		 */
		add(data?: any): Promise<BaseSysLogin_logAddResponse>;

		/**
		 * 删除
		 */
		delete(data?: any): Promise<any>;

		/**
		 * 获取详情
		 */
		info(data: { id: number }): Promise<login_log>;

		/**
		 * 获取列表
		 */
		list(data?: any): Promise<login_log[]>;

		/**
		 * 获取分页
		 */
		page(data?: any): Promise<BaseSysLogin_logPageResponse>;

		/**
		 * 更新
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
		 * 新增
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
		 * 快速创建菜单
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
		 * 获取当前用户菜单树
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
		 * 删除
		 */
		delete(data?: any): Promise<any>;

		/**
		 * 导出菜单
		 */
		export(data?: any): Promise<any[]>;

		/**
		 * 导入菜单
		 */
		import(data?: any): Promise<any>;

		/**
		 * 获取详情
		 */
		info(data: { id: number }): Promise<menu>;

		/**
		 * 获取列表
		 */
		list(data?: any): Promise<menu[]>;

		/**
		 * 获取分页
		 */
		page(data?: any): Promise<BaseSysMenuPageResponse>;

		/**
		 * 解析菜单候选
		 */
		parse(data?: any): Promise<BaseSysMenuParseResponse>;

		/**
		 * 获取角色菜单 ID 列表
		 */
		roleMenuIds(data: { role_id: number }): Promise<number[]>;

		/**
		 * 获取菜单树
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
		 * 更新
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
		 * 新增
		 */
		add(data?: any): Promise<BaseSysParamAddResponse>;

		/**
		 * 删除
		 */
		delete(data?: any): Promise<any>;

		/**
		 * 获得网页内容的参数值
		 */
		html(data: { key: string }): Promise<string>;

		/**
		 * 获取详情
		 */
		info(data: { id: number }): Promise<param>;

		/**
		 * 获取分页
		 */
		page(data?: any): Promise<BaseSysParamPageResponse>;

		/**
		 * 更新
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
		 * 新增
		 */
		add(data?: any): Promise<BaseSysRoleAddResponse>;

		/**
		 * 分配角色菜单
		 */
		assignMenus(data?: any): Promise<any>;

		/**
		 * 删除
		 */
		delete(data?: any): Promise<any>;

		/**
		 * 获取详情
		 */
		info(data: { id: number }): Promise<role>;

		/**
		 * 获取列表
		 */
		list(data?: any): Promise<role[]>;

		/**
		 * 获取分页
		 */
		page(data?: any): Promise<BaseSysRolePageResponse>;

		/**
		 * 更新
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
		 * 获取详情
		 */
		info(data: { id: number }): Promise<security_log>;

		/**
		 * 获取列表
		 */
		list(data?: any): Promise<security_log[]>;

		/**
		 * 获取分页
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
		 * 新增
		 */
		add(data?: any): Promise<BaseSysUserAddResponse>;

		/**
		 * 分配用户角色
		 */
		assignRoles(data?: any): Promise<BaseSysUserAssignRolesResponse>;

		/**
		 * 删除
		 */
		delete(data?: any): Promise<any>;

		/**
		 * 获取详情
		 */
		info(data: { id: number }): Promise<user>;

		/**
		 * 获取列表
		 */
		list(data?: any): Promise<user[]>;

		/**
		 * 获取当前登录用户信息
		 */
		me(data?: any): Promise<BaseSysUserMeResponse>;

		/**
		 * 移动部门
		 */
		move(data?: any): Promise<any>;

		/**
		 * 获取分页
		 */
		page(data?: any): Promise<BaseSysUserPageResponse>;

		/**
		 * 更新
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
		 * 新增
		 */
		add(data?: any): Promise<DictInfoAddResponse>;

		/**
		 * 获得字典数据
		 */
		data(data?: any): Promise<any>;

		/**
		 * 删除
		 */
		delete(data?: any): Promise<any>;

		/**
		 * 获取详情
		 */
		info(data: { id: number }): Promise<DictInfo>;

		/**
		 * 获取列表
		 */
		list(data?: any): Promise<DictInfo[]>;

		/**
		 * 获取分页
		 */
		page(data?: any): Promise<DictInfoPageResponse>;

		/**
		 * 获得所有字典类型
		 */
		types(data?: any): Promise<any[]>;

		/**
		 * 更新
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
		 * 新增
		 */
		add(data?: any): Promise<DictTypeAddResponse>;

		/**
		 * 删除
		 */
		delete(data?: any): Promise<any>;

		/**
		 * 获取详情
		 */
		info(data: { id: number }): Promise<DictType>;

		/**
		 * 获取列表
		 */
		list(data?: any): Promise<DictType[]>;

		/**
		 * 获取分页
		 */
		page(data?: any): Promise<DictTypePageResponse>;

		/**
		 * 更新
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
		 * 新增
		 */
		add(data?: any): Promise<MediaAssetAddResponse>;

		/**
		 * 删除
		 */
		delete(data?: any): Promise<any>;

		/**
		 * 签发短期下载令牌
		 */
		downloadToken(data?: any): Promise<any>;

		/**
		 * 获取详情
		 */
		info(data: { id: number }): Promise<asset>;

		/**
		 * 获取列表
		 */
		list(data?: any): Promise<asset[]>;

		/**
		 * 获取分页
		 */
		page(data?: any): Promise<MediaAssetPageResponse>;

		/**
		 * 远程媒体安全代理下载
		 */
		proxyImage(data: { url: string }): Promise<any>;

		/**
		 * 重试单个转存失败的媒体资产
		 */
		retry(data?: any): Promise<any>;

		/**
		 * 批量重试失败的媒体资产
		 */
		retryFailed(data?: any): Promise<any>;

		/**
		 * 媒体资源统计
		 */
		stats(data?: any): Promise<any>;

		/**
		 * 更新
		 */
		update(data?: any): Promise<MediaAssetUpdateResponse>;

		/**
		 * 上传媒体资源
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
		 * 新增
		 */
		add(data?: any): Promise<NotificationMessageAddResponse>;

		/**
		 * 归档通知
		 */
		archive(data?: any): Promise<any>;

		/**
		 * 删除
		 */
		delete(data?: any): Promise<any>;

		/**
		 * 获取详情
		 */
		info(data: { id: number }): Promise<message>;

		/**
		 * 获取列表
		 */
		list(data?: any): Promise<message[]>;

		/**
		 * 我的通知
		 */
		mine(data?: {
			includeArchived?: boolean;
			messageType?: string;
			readStatus?: string;
			limit?: number;
			offset?: number;
		}): Promise<any>;

		/**
		 * 我的通知详情
		 */
		myInfo(data: { id: number }): Promise<any>;

		/**
		 * 获取分页
		 */
		page(data?: any): Promise<NotificationMessagePageResponse>;

		/**
		 * 预览通知接收人
		 */
		previewRecipients(data?: any): Promise<any>;

		/**
		 * 标记已读
		 */
		read(data?: any): Promise<any>;

		/**
		 * 全部已读
		 */
		readAll(data?: any): Promise<any>;

		/**
		 * 撤回通知
		 */
		recall(data?: any): Promise<any>;

		/**
		 * 通知接收人明细
		 */
		recipients(data: { id: number }): Promise<any>;

		/**
		 * 发送通知
		 */
		send(data?: any): Promise<any>;

		/**
		 * 通知统计
		 */
		stats(data?: any): Promise<any>;

		/**
		 * 取消归档通知
		 */
		unarchive(data?: any): Promise<any>;

		/**
		 * 未读数量
		 */
		unreadCount(data?: any): Promise<any>;

		/**
		 * 更新
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
		 * 新增
		 */
		add(data?: any): Promise<NotificationRuleAddResponse>;

		/**
		 * 删除
		 */
		delete(data?: any): Promise<any>;

		/**
		 * 获取详情
		 */
		info(data: { id: number }): Promise<rule>;

		/**
		 * 获取列表
		 */
		list(data?: any): Promise<rule[]>;

		/**
		 * 获取分页
		 */
		page(data?: any): Promise<NotificationRulePageResponse>;

		/**
		 * 更新
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
		 * 新增
		 */
		add(data?: any): Promise<NotificationTemplateAddResponse>;

		/**
		 * 删除
		 */
		delete(data?: any): Promise<any>;

		/**
		 * 获取详情
		 */
		info(data: { id: number }): Promise<template>;

		/**
		 * 获取列表
		 */
		list(data?: any): Promise<template[]>;

		/**
		 * 获取分页
		 */
		page(data?: any): Promise<NotificationTemplatePageResponse>;

		/**
		 * 预览通知模板
		 */
		preview(data?: any): Promise<any>;

		/**
		 * 更新
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
		 * 新增
		 */
		add(data?: any): Promise<TaskInfoAddResponse>;

		/**
		 * 删除
		 */
		delete(data?: any): Promise<any>;

		/**
		 * 获取详情
		 */
		info(data: { id: number }): Promise<TaskInfo>;

		/**
		 * 获取列表
		 */
		list(data?: any): Promise<TaskInfo[]>;

		/**
		 * 任务日志
		 */
		log(data?: any): Promise<any>;

		/**
		 * 立即执行一次
		 */
		once(data?: any): Promise<any>;

		/**
		 * 获取分页
		 */
		page(data?: any): Promise<TaskInfoPageResponse>;

		/**
		 * 开始任务
		 */
		start(data?: any): Promise<any>;

		/**
		 * 停止任务
		 */
		stop(data?: any): Promise<any>;

		/**
		 * 更新
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
		 * 删除
		 */
		delete(data?: any): Promise<any>;

		/**
		 * 获取详情
		 */
		info(data: { id: number }): Promise<artifact>;

		/**
		 * 获取分页
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
		 * 新增
		 */
		add(data?: any): Promise<WorkflowDefinitionAddResponse>;

		/**
		 * 删除
		 */
		delete(data?: any): Promise<any>;

		/**
		 * 获取详情
		 */
		info(data: { id: number }): Promise<definition>;

		/**
		 * 获取列表
		 */
		list(data?: any): Promise<definition[]>;

		/**
		 * 获取分页
		 */
		page(data?: any): Promise<WorkflowDefinitionPageResponse>;

		/**
		 * 保存草稿
		 */
		saveDraft(data?: any): Promise<any>;

		/**
		 * 更新
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
		 * 取消运行中的工作流实例
		 */
		cancel(data?: any): Promise<any>;

		/**
		 * 删除
		 */
		delete(data?: any): Promise<any>;

		/**
		 * 获取详情
		 */
		info(data: { id: number }): Promise<instance>;

		/**
		 * 获取列表
		 */
		list(data?: any): Promise<instance[]>;

		/**
		 * 获取执行日志步骤列表
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
		 * 获取分页
		 */
		page(data?: any): Promise<WorkflowInstancePageResponse>;

		/**
		 * 提供人工确认恢复执行
		 */
		resume(data?: any): Promise<any>;

		/**
		 * 启动工作流实例
		 */
		start(data?: any): Promise<any>;

		/**
		 * SSE 实时推送工作流进度
		 */
		stream(data: { instanceId: number }): Promise<any>;

		/**
		 * 单节点测试运行
		 */
		testNode(data?: any): Promise<WorkflowInstanceTestNodeResponse>;

		/**
		 * 试运行工作流（草稿版）
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
		 * 两版本结构对比
		 */
		diff(data: { versionA: number; versionB: number }): Promise<any>;

		/**
		 * 获取详情
		 */
		info(data: { id: number }): Promise<version>;

		/**
		 * 获取列表
		 */
		list(data?: any): Promise<version[]>;

		/**
		 * 获取分页
		 */
		page(data?: any): Promise<WorkflowVersionPageResponse>;

		/**
		 * 发布草稿
		 */
		publish(data?: any): Promise<any>;

		/**
		 * 回滚到历史版本
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
		 * 新增
		 */
		add(data?: any): Promise<Workflow_annotationAnnotationAddResponse>;

		/**
		 * 删除
		 */
		delete(data?: any): Promise<any>;

		/**
		 * 获取详情
		 */
		info(data: { id: number }): Promise<annotation>;

		/**
		 * 计算 judge 与人工标注的 Cohen's κ
		 */
		kappa(data?: any): Promise<any>;

		/**
		 * 获取列表
		 */
		list(data?: any): Promise<annotation[]>;

		/**
		 * 获取分页
		 */
		page(data?: any): Promise<Workflow_annotationAnnotationPageResponse>;

		/**
		 * 更新
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
		 * 取消评估运行
		 */
		cancel(data?: any): Promise<any>;

		/**
		 * 查看评估用例结果
		 */
		cases(data: { evalRunId: number; page?: number; size?: number }): Promise<any>;

		/**
		 * 两次评估的回归对比
		 */
		compare(data: { runA: number; runB: number }): Promise<any>;

		/**
		 * 删除
		 */
		delete(data?: any): Promise<any>;

		/**
		 * 获取详情
		 */
		info(data: { id: number }): Promise<eval_run>;

		/**
		 * 获取列表
		 */
		list(data?: any): Promise<eval_run[]>;

		/**
		 * 获取分页
		 */
		page(data?: any): Promise<Workflow_evalEval_runPageResponse>;

		/**
		 * 轮询评估运行结果（CI 门禁用）
		 */
		poll(data: {
			evalRunId: number;
			/** 最长等待秒数  */
			timeout?: number;
			/** 轮询间隔秒数  */
			interval?: number;
		}): Promise<any>;

		/**
		 * 采样生产实例入黄金集（在线评测）
		 */
		sampleProduction(data?: any): Promise<any>;

		/**
		 * 发起批量评估
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
		 * 新增
		 */
		add(data?: any): Promise<Workflow_evalTest_caseAddResponse>;

		/**
		 * 删除
		 */
		delete(data?: any): Promise<any>;

		/**
		 * 获取详情
		 */
		info(data: { id: number }): Promise<test_case>;

		/**
		 * 获取列表
		 */
		list(data?: any): Promise<test_case[]>;

		/**
		 * 获取分页
		 */
		page(data?: any): Promise<Workflow_evalTest_casePageResponse>;

		/**
		 * 更新
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
		 * 新增
		 */
		add(data?: any): Promise<Workflow_evalTest_setAddResponse>;

		/**
		 * 删除
		 */
		delete(data?: any): Promise<any>;

		/**
		 * 批量导入测试用例
		 */
		importCases(data?: any): Promise<any>;

		/**
		 * 获取详情
		 */
		info(data: { id: number }): Promise<test_set>;

		/**
		 * 获取列表
		 */
		list(data?: any): Promise<test_set[]>;

		/**
		 * 获取分页
		 */
		page(data?: any): Promise<Workflow_evalTest_setPageResponse>;

		/**
		 * 更新
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
