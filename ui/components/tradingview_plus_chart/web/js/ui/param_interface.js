// web/js/ui/param_interface.js
class ParameterInterface {
    constructor() {
        this.currentIndicator = null;
        this.currentParams = {};
        this.paramElements = {};
    }
    
    showParameterForm(indicatorConfig, currentParams = {}) {
        console.log('📋 显示参数表单:', indicatorConfig.name);
        
        this.currentIndicator = indicatorConfig.id;
        this.currentParams = { ...currentParams };
        
        // 创建模态对话框
        this.createModal(indicatorConfig);
    }
    
    createModal(indicatorConfig) {
        // 创建模态框HTML
        const modalHtml = `
        <div class="param-modal" id="paramModal">
            <div class="modal-content">
                <div class="modal-header">
                    <h3>${indicatorConfig.name} - 参数设置</h3>
                    <button class="close-btn">&times;</button>
                </div>
                <div class="modal-body">
                    <div class="indicator-info">
                        <p><strong>描述:</strong> ${indicatorConfig.description}</p>
                        <p><strong>显示位置:</strong> ${indicatorConfig.chart === 'main' ? '主图' : '副图'}</p>
                    </div>
                    <form id="paramForm" class="param-form">
                        <!-- 参数字段将动态生成 -->
                    </form>
                </div>
                <div class="modal-footer">
                    <button type="button" class="btn btn-secondary" id="cancelBtn">取消</button>
                    <button type="button" class="btn btn-primary" id="applyBtn">应用</button>
                </div>
            </div>
        </div>
        `;
        
        // 添加到页面
        document.body.insertAdjacentHTML('beforeend', modalHtml);
        
        // 生成参数表单
        this.generateParamForm(indicatorConfig.parameters);
        
        // 绑定事件
        this.bindModalEvents();
    }
    
    generateParamForm(parameters) {
        const form = document.getElementById('paramForm');
        form.innerHTML = '';
        
        for (const [key, param] of Object.entries(parameters)) {
            const fieldHtml = this.createParamField(key, param);
            form.insertAdjacentHTML('beforeend', fieldHtml);
            
            // 设置当前值
            if (this.currentParams[key] !== undefined) {
                this.setFieldValue(key, this.currentParams[key]);
            }
        }
    }
    
    createParamField(key, param) {
        const value = this.currentParams[key] || param.default;
        
        switch (param.type) {
            case 'int':
            case 'float':
                return `
                <div class="form-group">
                    <label for="${key}">${param.name}:</label>
                    <input type="number" id="${key}" 
                           value="${value}" 
                           min="${param.min || ''}" 
                           max="${param.max || ''}"
                           step="${param.type === 'float' ? '0.01' : '1'}"
                           ${param.required ? 'required' : ''}>
                    <small class="form-text">${param.description || ''}</small>
                </div>
                `;
                
            case 'select':
                const options = param.options.map(opt => {
                    const label = typeof opt === 'object' ? opt.label : opt;
                    const val = typeof opt === 'object' ? opt.value : opt;
                    const selected = val === value ? 'selected' : '';
                    return `<option value="${val}" ${selected}>${label}</option>`;
                }).join('');
                
                return `
                <div class="form-group">
                    <label for="${key}">${param.name}:</label>
                    <select id="${key}" ${param.required ? 'required' : ''}>
                        ${options}
                    </select>
                    <small class="form-text">${param.description || ''}</small>
                </div>
                `;
                
            case 'color':
                return `
                <div class="form-group">
                    <label for="${key}">${param.name}:</label>
                    <input type="color" id="${key}" 
                           value="${value || '#2962FF'}"
                           ${param.required ? 'required' : ''}>
                    <small class="form-text">${param.description || ''}</small>
                </div>
                `;
                
            default:
                return `
                <div class="form-group">
                    <label for="${key}">${param.name}:</label>
                    <input type="text" id="${key}" 
                           value="${value || ''}"
                           ${param.required ? 'required' : ''}>
                    <small class="form-text">${param.description || ''}</small>
                </div>
                `;
        }
    }
    
    collectParameters() {
        const params = {};
        const form = document.getElementById('paramForm');
        
        for (const [key, param] of Object.entries(this.currentIndicator?.parameters || {})) {
            const element = document.getElementById(key);
            if (element) {
                let value = element.value;
                
                // 类型转换
                if (param.type === 'int') {
                    value = parseInt(value, 10);
                } else if (param.type === 'float') {
                    value = parseFloat(value);
                } else if (param.type === 'bool') {
                    value = Boolean(value);
                }
                
                // 验证
                if (param.required && (value === undefined || value === '')) {
                    alert(`参数 "${param.name}" 是必填项`);
                    return null;
                }
                
                params[key] = value;
            }
        }
        
        return params;
    }
    
    bindModalEvents() {
        const modal = document.getElementById('paramModal');
        const closeBtn = modal.querySelector('.close-btn');
        const cancelBtn = modal.querySelector('#cancelBtn');
        const applyBtn = modal.querySelector('#applyBtn');
        
        const closeModal = () => {
            document.body.removeChild(modal);
        };
        
        closeBtn.addEventListener('click', closeModal);
        cancelBtn.addEventListener('click', closeModal);
        
        applyBtn.addEventListener('click', () => {
            const params = this.collectParameters();
            if (params) {
                // 通知Python应用参数
                if (window.pythonBridge && window.pythonBridge.notify) {
                    window.pythonBridge.notify('apply_parameters', {
                        indicator: this.currentIndicator.id,
                        parameters: params
                    });
                }
                closeModal();
            }
        });
        
        // 点击背景关闭
        modal.addEventListener('click', (e) => {
            if (e.target === modal) {
                closeModal();
            }
        });
    }
}