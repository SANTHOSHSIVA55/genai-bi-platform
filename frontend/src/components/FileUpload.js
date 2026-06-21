import React, { useCallback, useState } from 'react';
import { useDropzone } from 'react-dropzone';
import { motion, AnimatePresence } from 'framer-motion';
import { Upload, FileSpreadsheet, FileText, Check, X, Loader2 } from 'lucide-react';
import { uploadDataset } from '../api/api';
import toast from 'react-hot-toast';

const FileUpload = ({ onUploadSuccess }) => {
  const [uploading, setUploading] = useState(false);
  const [uploadedFile, setUploadedFile] = useState(null);
  const [datasetName, setDatasetName] = useState('');

  const onDrop = useCallback((acceptedFiles) => {
    if (acceptedFiles.length > 0) {
      setUploadedFile(acceptedFiles[0]);
      setDatasetName(acceptedFiles[0].name.replace(/\.[^/.]+$/, ''));
    }
  }, []);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: {
      'text/csv': ['.csv'],
      'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': ['.xlsx'],
      'application/vnd.ms-excel': ['.xls'],
      'application/pdf': ['.pdf'],
    },
    maxFiles: 1,
    maxSize: 50 * 1024 * 1024,
  });

  const handleUpload = async () => {
    if (!uploadedFile) return;
    setUploading(true);

    const formData = new FormData();
    formData.append('file', uploadedFile);
    if (datasetName) formData.append('name', datasetName);

    try {
      const res = await uploadDataset(formData);
      toast.success(`Dataset "${res.data.name}" uploaded successfully!`);
      setUploadedFile(null);
      setDatasetName('');
      if (onUploadSuccess) onUploadSuccess(res.data);
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Upload failed');
    } finally {
      setUploading(false);
    }
  };

  const getFileIcon = (name) => {
    const ext = name?.split('.').pop()?.toLowerCase();
    if (ext === 'pdf') return <FileText className="w-8 h-8 text-red-400" />;
    return <FileSpreadsheet className="w-8 h-8 text-emerald-400" />;
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      className="glass-card p-6"
    >
      <h2 className="text-lg font-semibold text-dark-100 mb-4 flex items-center gap-2">
        <Upload className="w-5 h-5 text-primary-400" />
        Upload Dataset
      </h2>

      <AnimatePresence mode="wait">
        {!uploadedFile ? (
          <motion.div
            key="dropzone"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            {...getRootProps()}
            className={`border-2 border-dashed rounded-2xl p-10 text-center cursor-pointer transition-all duration-300 ${
              isDragActive
                ? 'border-primary-500 bg-primary-500/10'
                : 'border-dark-600 hover:border-primary-500/50 hover:bg-dark-800/50'
            }`}
          >
            <input {...getInputProps()} />
            <div className="flex flex-col items-center gap-3">
              <div className="w-16 h-16 rounded-xl bg-gradient-to-br from-primary-500/20 to-amber-500/10 flex items-center justify-center border border-primary-500/10">
                <Upload className="w-8 h-8 text-primary-400" />
              </div>
              <p className="text-dark-200 font-medium">
                {isDragActive ? 'Drop your file here...' : 'Drag & drop your file here'}
              </p>
              <p className="text-dark-500 text-sm">CSV, Excel (.xlsx), or PDF — up to 50MB</p>
            </div>
          </motion.div>
        ) : (
          <motion.div
            key="preview"
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0 }}
            className="space-y-4"
          >
            <div className="flex items-center gap-4 p-4 bg-dark-800 rounded-xl border border-dark-600">
              {getFileIcon(uploadedFile.name)}
              <div className="flex-1">
                <p className="text-dark-100 font-medium">{uploadedFile.name}</p>
                <p className="text-dark-500 text-sm">
                  {(uploadedFile.size / (1024 * 1024)).toFixed(2)} MB
                </p>
              </div>
              <button
                onClick={() => { setUploadedFile(null); setDatasetName(''); }}
                className="min-h-[44px] min-w-[44px] flex items-center justify-center p-2.5 hover:bg-red-500/10 rounded-lg text-dark-400 hover:text-red-400 transition-colors"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <input
              type="text"
              placeholder="Dataset name (optional)"
              value={datasetName}
              onChange={(e) => setDatasetName(e.target.value)}
              className="input-field"
            />

            <button
              onClick={handleUpload}
              disabled={uploading}
              className="btn-primary w-full flex items-center justify-center gap-2"
            >
              {uploading ? (
                <>
                  <Loader2 className="w-5 h-5 animate-spin" />
                  Processing...
                </>
              ) : (
                <>
                  <Check className="w-5 h-5" />
                  Upload & Clean Data
                </>
              )}
            </button>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
};

export default FileUpload;
